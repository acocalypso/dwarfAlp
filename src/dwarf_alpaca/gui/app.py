from __future__ import annotations

import html
import logging
import sys
import time
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx
import structlog
import yaml
from PySide6.QtCore import QLockFile, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QKeySequence, QPalette, QPixmap, QTextCursor
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QCheckBox,
    QComboBox,
    QCompleter,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplashScreen,
    QSplitter,
    QStyleFactory,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

try:
    from zoneinfo import available_timezones
except Exception:  # pragma: no cover - Python < 3.9 or missing tzdata
    available_timezones = None  # type: ignore[assignment]

from .. import __version__
from ..cli import _configure_start_logging, _preflight_session
from ..config.settings import Settings, load_settings, normalize_dwarf_device_model
from ..dwarf.ble_provisioner import DwarfBleProvisioner, ProvisioningError
from ..dwarf.state import ConnectivityState, StateStore
from ..provisioning.workflow import create_state_store, provision_sta
from .activity import COLORS, ICONS, ActivityEntry, ActivityTranslator
from .logging import ActivityLogHandler, QtLogHandler
from .server import ServerService, ServerStatus
from .workers import AsyncWorker

logger = logging.getLogger(__name__)


APP_ICON_PATH = Path(__file__).resolve().parents[3] / "images" / "dwarfalplogo.ico"
SPLASH_PATH = APP_ICON_PATH.with_name("splash.png")


def _configure_gui_structlog() -> None:
    """Route structured logs through stdlib in windowed/frozen applications.

    PyInstaller's ``--windowed`` bootloader sets ``sys.stdout`` and
    ``sys.stderr`` to ``None``. Structlog's default print logger cannot create
    its per-stream weak-reference lock for ``None``, so background-task cleanup
    would otherwise fail while trying to log.
    """

    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.stdlib.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
    )


def _load_timezone_choices() -> list[str]:
    if callable(available_timezones):
        try:
            candidates = available_timezones()
        except Exception:  # pragma: no cover - defensive fallback
            candidates = {"UTC"}
        choices = [
            tz
            for tz in candidates
            if isinstance(tz, str) and "/" in tz and not tz.startswith("Etc/") and tz[0].isalpha()
        ]
        if "UTC" not in choices:
            choices.append("UTC")
        return sorted(choices)
    return ["UTC"]


TIMEZONE_CHOICES = _load_timezone_choices()


DWARF_MODEL_CHOICES: list[tuple[str, str, str]] = [
    ("DWARF 3", "dwarf3", "0000DAF3-0000-1000-8000-00805F9B34FB"),
    ("DWARF 2", "dwarf2", "0000DAF2-0000-1000-8000-00805F9B34FB"),
    ("DWARF mini", "dwarfmini", "0000DAF4-0000-1000-8000-00805F9B34FB"),
]

WS_CLIENT_CHOICES: list[tuple[str, str]] = [
    (label, client_id) for label, _, client_id in DWARF_MODEL_CHOICES
]

_MODEL_DEFAULT_CLIENT_ID = {model: client_id for _, model, client_id in DWARF_MODEL_CHOICES}
_CLIENT_ID_MODEL = {client_id: model for _, model, client_id in DWARF_MODEL_CHOICES}


def _infer_dwarf_model_from_name(name: str) -> str | None:
    normalized = " ".join((name or "").lower().replace("_", " ").replace("-", " ").split())
    compact = normalized.replace(" ", "")
    if "mini" in normalized or "dwarf4" in compact:
        return "dwarfmini"
    if "dwarf3" in compact:
        return "dwarf3"
    if "dwarf2" in compact or "dwarfii" in compact:
        return "dwarf2"
    return None


@dataclass
class WifiNetwork:
    ssid: str
    signal: Optional[int] = None


class LogConsole(QTextEdit):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setLineWrapMode(QTextEdit.NoWrap)

    def append_message(self, level: int, message: str) -> None:
        color = {
            logging.DEBUG: "#888888",
            logging.INFO: "#1c6fbb",
            logging.WARNING: "#d17c00",
            logging.ERROR: "#b00020",
            logging.CRITICAL: "#7f0000",
        }.get(level, "#333333")
        formatted = f'<span style="color:{color}">{message}</span>'
        self.append(formatted)
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())


class ActivityConsole(QTextEdit):
    """Plain-language activity feed; repeated messages are merged (×N)."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self._last_group: Optional[str] = None
        self._last_entry: Optional[ActivityEntry] = None
        self._repeat = 0

    def append_entry(self, entry: ActivityEntry) -> None:
        if entry.group and entry.group == self._last_group and self._last_entry:
            self._repeat += 1
            self._remove_last_line()
            self._write(entry, self._repeat)
        else:
            self._repeat = 1
            self._write(entry, 1)
        self._last_group = entry.group
        self._last_entry = entry
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())

    def _write(self, entry: ActivityEntry, repeat: int) -> None:
        stamp = time.strftime("%H:%M:%S", time.localtime(entry.timestamp))
        color = COLORS.get(entry.kind, "#333333")
        icon = ICONS.get(entry.kind, "•")
        suffix = f" <b>(×{repeat})</b>" if repeat > 1 else ""
        self.append(
            f'<span style="color:#888888">{stamp}</span>&nbsp;&nbsp;'
            f'<span style="color:{color}">{icon}&nbsp;{html.escape(entry.text)}</span>{suffix}'
        )

    def _remove_last_line(self) -> None:
        document = self.document()
        if document.blockCount() <= 1:
            self.clear()
            return
        # Select from the end of the previous block to the end of the document,
        # i.e. the last line together with its preceding paragraph separator.
        cursor = QTextCursor(document)
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        cursor.movePosition(
            QTextCursor.MoveOperation.PreviousCharacter, QTextCursor.MoveMode.MoveAnchor
        )
        cursor.movePosition(QTextCursor.MoveOperation.End, QTextCursor.MoveMode.KeepAnchor)
        cursor.removeSelectedText()


IP_FIELD_WIDTH = 140


def _compact_form() -> QFormLayout:
    """Form where only text such as wrapped labels fills the row.

    Value fields get a fixed width (see the widgets), so they no longer stretch
    across the whole tab.
    """

    form = QFormLayout()
    form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
    return form


def _inline_row(*items: QWidget | str) -> QWidget:
    """Lay out several fields on one form row (strings become small labels)."""

    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    for index, item in enumerate(items):
        if isinstance(item, str):
            label = QLabel(item)
            if index:
                label.setContentsMargins(12, 0, 0, 0)
            layout.addWidget(label)
        else:
            layout.addWidget(item)
    layout.addStretch(1)
    return row


class SettingsOverridesWidget(QGroupBox):
    location_fetch_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__("Server Overrides", parent)
        form = _compact_form()

        self.http_host_edit = QLineEdit()
        self.http_port_spin = QSpinBox()
        self.http_port_spin.setRange(1, 65535)
        self.dwarf_ip_edit = QLineEdit()
        self.device_model_combo = QComboBox()
        for label, value, _ in DWARF_MODEL_CHOICES:
            self.device_model_combo.addItem(label, value)
        self.ws_client_id_combo = QComboBox()
        self.ws_client_id_combo.setEditable(True)
        for label, value in WS_CLIENT_CHOICES:
            display = f"{label} ({value})"
            self.ws_client_id_combo.addItem(display, value)
        self.ws_client_id_combo.setInsertPolicy(QComboBox.NoInsert)
        self.force_sim_checkbox = QCheckBox("Force simulation mode")
        self.skip_preflight_checkbox = QCheckBox("Skip connectivity preflight")
        self.calibrate_after_start_checkbox = QCheckBox("Prepare calibration after start")
        self.site_latitude_edit = QLineEdit()
        self.site_latitude_edit.setPlaceholderText("e.g. 48.1372")
        self.site_longitude_edit = QLineEdit()
        self.site_longitude_edit.setPlaceholderText("e.g. 11.5756")
        self.fetch_location_button = QPushButton("Fetch current position")
        self.fetch_location_button.setToolTip(
            "Estimate coordinates from your public IP using the configured web service."
        )
        self.fetch_location_button.clicked.connect(self.location_fetch_requested.emit)
        self.location_status_label = QLabel()
        self.location_status_label.setWordWrap(True)
        self.preflight_timeout_spin = QSpinBox()
        self.preflight_timeout_spin.setRange(5, 1800)
        self.preflight_timeout_spin.setSuffix(" s")
        self.preflight_interval_spin = QSpinBox()
        self.preflight_interval_spin.setRange(1, 120)
        self.preflight_interval_spin.setSuffix(" s")
        self.timezone_combo = QComboBox()
        self.timezone_combo.setEditable(True)
        self.timezone_combo.setInsertPolicy(QComboBox.NoInsert)
        self.timezone_combo.setMinimumContentsLength(30)
        completer = QCompleter(TIMEZONE_CHOICES, self.timezone_combo)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        self.timezone_combo.setCompleter(completer)
        self.timezone_combo.addItem("Use system timezone (default)", None)
        for tz in TIMEZONE_CHOICES:
            self.timezone_combo.addItem(tz, tz)

        self.device_model_combo.currentIndexChanged.connect(self._sync_client_id_for_selected_model)
        self.device_model_combo.currentIndexChanged.connect(self._sync_calibration_availability)

        # Compact layout: related fields share a row so the log area can be taller.
        self.http_host_edit.setFixedWidth(IP_FIELD_WIDTH)
        self.http_port_spin.setFixedWidth(90)
        self.dwarf_ip_edit.setFixedWidth(IP_FIELD_WIDTH)
        for combo in (self.device_model_combo, self.ws_client_id_combo, self.timezone_combo):
            combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
            combo.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.site_latitude_edit.setFixedWidth(110)
        self.site_longitude_edit.setFixedWidth(110)
        self.preflight_timeout_spin.setFixedWidth(90)
        self.preflight_interval_spin.setFixedWidth(80)

        form.addRow("HTTP host", _inline_row(self.http_host_edit, "Port", self.http_port_spin))
        form.addRow("DWARF IP", self.dwarf_ip_edit)
        form.addRow("DWARF model", self.device_model_combo)
        form.addRow("WS client ID", self.ws_client_id_combo)
        form.addRow(
            _inline_row(
                self.force_sim_checkbox,
                self.skip_preflight_checkbox,
                self.calibrate_after_start_checkbox,
            )
        )
        form.addRow(
            "Site",
            _inline_row(
                self.fetch_location_button,
                "Latitude",
                self.site_latitude_edit,
                "Longitude",
                self.site_longitude_edit,
            ),
        )
        form.addRow("Location status", self.location_status_label)
        form.addRow(
            "Preflight",
            _inline_row(
                "Timeout", self.preflight_timeout_spin, "Interval", self.preflight_interval_spin
            ),
        )
        form.addRow("Timezone", self.timezone_combo)
        self.setLayout(form)

    def populate(self, settings: Settings) -> None:
        self.http_host_edit.setText(settings.http_host)
        self.http_port_spin.setValue(settings.http_port)
        self.dwarf_ip_edit.setText(settings.dwarf_ap_ip)
        model = normalize_dwarf_device_model(settings.dwarf_device_model)
        model_index = self.device_model_combo.findData(model)
        if model_index >= 0:
            self.device_model_combo.setCurrentIndex(model_index)
        index = self.ws_client_id_combo.findData(settings.dwarf_ws_client_id)
        if index >= 0:
            self.ws_client_id_combo.setCurrentIndex(index)
        else:
            self.ws_client_id_combo.setEditText(settings.dwarf_ws_client_id)
        self.force_sim_checkbox.setChecked(settings.force_simulation)
        self.skip_preflight_checkbox.setChecked(False)
        self.calibrate_after_start_checkbox.setChecked(settings.calibrate_after_server_start)
        self.set_site_location(settings.site_latitude, settings.site_longitude)
        self._sync_calibration_availability()
        self.preflight_timeout_spin.setValue(180)
        self.preflight_interval_spin.setValue(5)
        self.set_timezone_name(settings.timezone_name)

    def apply(self, settings: Settings) -> Settings:
        data = settings.model_dump()
        selected_model = normalize_dwarf_device_model(self.device_model_combo.currentData())
        selected_client_id = self.ws_client_id_combo.currentData()
        if not isinstance(selected_client_id, str) or not selected_client_id.strip():
            selected_client_id = self.ws_client_id_combo.currentText().strip()
        selected_client_id = selected_client_id or settings.dwarf_ws_client_id
        selected_model = _CLIENT_ID_MODEL.get(selected_client_id, selected_model)
        combo_index = self.timezone_combo.currentIndex()
        combo_data = self.timezone_combo.itemData(combo_index) if combo_index >= 0 else None
        timezone_name = None
        if isinstance(combo_data, str) and combo_data.strip():
            timezone_name = combo_data.strip()
        else:
            text_value = self.timezone_combo.currentText().strip()
            timezone_name = text_value or None
        data.update(
            {
                "http_host": self.http_host_edit.text().strip() or settings.http_host,
                "http_port": self.http_port_spin.value(),
                "dwarf_ap_ip": self.dwarf_ip_edit.text().strip() or settings.dwarf_ap_ip,
                "dwarf_device_model": selected_model,
                "dwarf_ws_client_id": selected_client_id,
                "force_simulation": self.force_sim_checkbox.isChecked(),
                "calibrate_after_server_start": (
                    self.calibrate_after_start_checkbox.isChecked()
                ),
                "site_latitude": self._parse_optional_coordinate(
                    self.site_latitude_edit.text(), "Latitude", -90.0, 90.0
                ),
                "site_longitude": self._parse_optional_coordinate(
                    self.site_longitude_edit.text(), "Longitude", -180.0, 180.0
                ),
                "timezone_name": timezone_name,
            }
        )
        return settings.model_validate(data)

    @staticmethod
    def _parse_optional_coordinate(
        text: str, label: str, minimum: float, maximum: float
    ) -> float | None:
        normalized = text.strip().replace(",", ".")
        if not normalized:
            return None
        try:
            value = float(normalized)
        except ValueError as exc:
            raise ValueError(f"{label} must be a decimal number") from exc
        if not minimum <= value <= maximum:
            raise ValueError(f"{label} must be between {minimum:g} and {maximum:g}")
        return value

    def set_site_location(self, latitude: float | None, longitude: float | None) -> None:
        self.site_latitude_edit.setText("" if latitude is None else f"{latitude:.6f}")
        self.site_longitude_edit.setText("" if longitude is None else f"{longitude:.6f}")

    def set_location_lookup_busy(self, busy: bool, message: str = "") -> None:
        self.fetch_location_button.setEnabled(not busy)
        self.location_status_label.setText(message)

    def set_device_model(self, model: str) -> None:
        normalized = normalize_dwarf_device_model(model)
        index = self.device_model_combo.findData(normalized)
        if index >= 0:
            self.device_model_combo.setCurrentIndex(index)
            self._sync_client_id_for_selected_model()

    def _sync_client_id_for_selected_model(self) -> None:
        model = normalize_dwarf_device_model(self.device_model_combo.currentData())
        target_client_id = _MODEL_DEFAULT_CLIENT_ID.get(model)
        if not target_client_id:
            return

        current_client_id = self.ws_client_id_combo.currentData()
        if not isinstance(current_client_id, str) or not current_client_id.strip():
            current_client_id = self.ws_client_id_combo.currentText().strip()

        # Respect custom UUIDs; only auto-switch known built-in IDs.
        if current_client_id and current_client_id not in _MODEL_DEFAULT_CLIENT_ID.values():
            return

        idx = self.ws_client_id_combo.findData(target_client_id)
        if idx >= 0:
            self.ws_client_id_combo.setCurrentIndex(idx)
        else:
            self.ws_client_id_combo.setEditText(target_client_id)

    def _sync_calibration_availability(self) -> None:
        self.calibrate_after_start_checkbox.setEnabled(True)
        self.calibrate_after_start_checkbox.setToolTip(
            "Run autofocus after server start. Target-based V3 calibration and movement "
            "begin with the first NINA GoTo."
        )

    def set_timezone_name(self, name: Optional[str]) -> None:
        if not isinstance(name, str) or not name.strip():
            self.timezone_combo.setCurrentIndex(0)
            self.timezone_combo.setEditText("")
            return
        normalized = name.strip()
        index = self.timezone_combo.findData(normalized)
        if index >= 0:
            self.timezone_combo.setCurrentIndex(index)
        else:
            self.timezone_combo.setEditText(normalized)


class ProvisioningWidget(QGroupBox):
    provision_requested = Signal(dict)
    discovery_requested = Signal(dict)
    wifi_scan_requested = Signal(dict)
    device_selected = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__("Provisioning", parent)
        layout = QVBoxLayout()

        form = _compact_form()
        self.ssid_edit = QLineEdit()
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.show_password_checkbox = QCheckBox("Show password")
        self.ble_password_edit = QLineEdit()
        self.device_address_edit = QLineEdit()

        for field in (self.ssid_edit, self.password_edit, self.device_address_edit):
            field.setFixedWidth(240)
        self.ble_password_edit.setFixedWidth(160)
        form.addRow("SSID", self.ssid_edit)
        form.addRow("Password", self.password_edit)
        form.addRow("", self.show_password_checkbox)
        form.addRow("BLE password", self.ble_password_edit)
        form.addRow("Device address", self.device_address_edit)
        layout.addLayout(form)

        buttons_layout = QHBoxLayout()
        self.discover_button = QPushButton("Discover devices")
        self.provision_button = QPushButton("Provision Wi-Fi")
        self.scan_wifi_button = QPushButton("Fetch Wi-Fi list")
        buttons_layout.addWidget(self.discover_button)
        buttons_layout.addWidget(self.scan_wifi_button)
        buttons_layout.addWidget(self.provision_button)
        layout.addLayout(buttons_layout)

        lists_layout = QHBoxLayout()
        self.devices_list = QListWidget()
        self.devices_list.setSelectionMode(QListWidget.SingleSelection)
        self.devices_list.setMinimumWidth(220)
        self.wifi_list = QListWidget()
        lists_layout.addWidget(self.devices_list)
        lists_layout.addWidget(self.wifi_list)
        layout.addLayout(lists_layout)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.setLayout(layout)

        self.discover_button.clicked.connect(self._emit_discover)
        self.provision_button.clicked.connect(self._emit_provision)
        self.scan_wifi_button.clicked.connect(self._emit_scan_wifi)
        self.devices_list.itemSelectionChanged.connect(self._handle_device_selected)
        self.wifi_list.itemClicked.connect(self._handle_wifi_selected)
        self.show_password_checkbox.toggled.connect(self._toggle_password_visibility)

    def _emit_discover(self) -> None:
        self.discovery_requested.emit({})

    def _emit_provision(self) -> None:
        payload = {
            "ssid": self.ssid_edit.text().strip(),
            "password": self.password_edit.text(),
            "ble_password": self.ble_password_edit.text().strip() or None,
            "device_address": self.device_address_edit.text().strip() or None,
        }
        self.provision_requested.emit(payload)

    def _emit_scan_wifi(self) -> None:
        payload = {
            "ble_password": self.ble_password_edit.text().strip() or None,
            "device_address": self.device_address_edit.text().strip() or None,
        }
        self.wifi_scan_requested.emit(payload)

    def _handle_device_selected(self) -> None:
        item = self.devices_list.currentItem()
        if not item:
            return
        address = item.data(Qt.UserRole)
        if isinstance(address, str):
            self.device_address_edit.setText(address)
            self.device_selected.emit(address)

    def _handle_wifi_selected(self, item: QListWidgetItem) -> None:
        ssid = item.text()
        if ssid:
            self.ssid_edit.setText(ssid)

    def _toggle_password_visibility(self, checked: bool) -> None:
        self.password_edit.setEchoMode(QLineEdit.Normal if checked else QLineEdit.Password)

    def show_status(self, message: str) -> None:
        self.status_label.setText(message)

    def populate_devices(self, devices: list[tuple[str, str]]) -> None:
        self.devices_list.clear()
        for name, address in devices:
            display = f"{name} ({address})" if address else name
            item = QListWidgetItem(display)
            item.setData(Qt.UserRole, address)
            self.devices_list.addItem(item)

    def populate_wifi(self, networks: list[str]) -> None:
        self.wifi_list.clear()
        for ssid in networks:
            self.wifi_list.addItem(ssid)

    def populate_saved_credentials(self, ssid: Optional[str], password: Optional[str]) -> None:
        self.ssid_edit.setText(ssid or "")
        self.password_edit.setText(password or "")
        self.show_password_checkbox.blockSignals(True)
        self.show_password_checkbox.setChecked(False)
        self.show_password_checkbox.blockSignals(False)
        self.password_edit.setEchoMode(QLineEdit.Password)

    def set_ble_password(self, password: Optional[str]) -> None:
        value = password or "DWARF_12345678"
        self.ble_password_edit.setText(value)

    def set_device_address(self, address: Optional[str]) -> None:
        self.device_address_edit.setText(address or "")

    def current_payload(self) -> dict[str, Optional[str]]:
        return {
            "ssid": self.ssid_edit.text().strip(),
            "password": self.password_edit.text(),
            "ble_password": self.ble_password_edit.text().strip() or None,
            "device_address": self.device_address_edit.text().strip() or None,
        }


class ServerControlWidget(QGroupBox):
    start_requested = Signal()
    stop_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__("Server", parent)
        layout = QVBoxLayout()

        button_layout = QHBoxLayout()
        self.start_button = QPushButton("Start server")
        self.stop_button = QPushButton("Stop server")
        self.stop_button.setEnabled(False)
        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.stop_button)
        layout.addLayout(button_layout)

        self.status_label = QLabel("Stopped")
        layout.addWidget(self.status_label)

        self.master_lock_label = QLabel("Master lock status: unknown")
        self.master_lock_hint_label = QLabel()
        self.master_lock_hint_label.setWordWrap(True)
        self.battery_label = QLabel("Battery status: unknown")
        self.calibration_label = QLabel("Calibration status: unknown")
        self.calibration_label.setWordWrap(True)
        layout.addWidget(self.master_lock_label)
        layout.addWidget(self.battery_label)
        layout.addWidget(self.calibration_label)
        layout.addWidget(self.master_lock_hint_label)

        self.setLayout(layout)

        self.start_button.clicked.connect(self.start_requested)
        self.stop_button.clicked.connect(self.stop_requested)
        self.set_master_lock_status(None)

    def set_running(self, running: bool, message: str) -> None:
        self.status_label.setText(message)
        self.start_button.setEnabled(not running)
        self.stop_button.setEnabled(running)

    def set_busy(self, message: str) -> None:
        self.status_label.setText(message)
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(False)

    def set_master_lock_status(self, has_lock: Optional[bool]) -> None:
        if has_lock is None:
            status_text = "Master lock status: unknown"
            hint_text = ""
        elif has_lock:
            status_text = "Master lock status: acquired"
            hint_text = ""
        else:
            status_text = "Master lock status: not acquired"
            hint_text = "Stop the server, shutdown the DWARF, do not use your phone app to connect to the DWARF as this will take the master lock."
        self.master_lock_label.setText(status_text)
        self.master_lock_hint_label.setText(hint_text)
        self.master_lock_hint_label.setVisible(bool(hint_text))

    def set_battery_status(self, battery_percent: Optional[int]) -> None:
        if battery_percent is None:
            text = "Battery status: unknown"
        else:
            text = f"Battery status: {battery_percent}%"
        self.battery_label.setText(text)

    def set_calibration_status(
        self, status: Optional[str], detail: Optional[str] = None
    ) -> None:
        status_text = status or "unknown"
        text = f"Calibration status: {status_text}"
        if detail:
            text += f" ({detail})"
        self.calibration_label.setText(text)


def _load_app_icon() -> QIcon:
    if APP_ICON_PATH.exists():
        return QIcon(str(APP_ICON_PATH))
    logger.warning("gui.icon.missing path=%s", APP_ICON_PATH)
    return QIcon()


def _resolve_state_directory(path: Path) -> Path:
    if path.is_absolute():
        return path
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).resolve().parent
    else:
        base = Path.cwd()
    return (base / path).resolve()


TESTED_ENVIRONMENT = (
    "DWARF 3 firmware V1.5.4.1 and V1.5.5.1, DWARFLAB app V3.4.5 (build 794), N.I.N.A. 3.2.0.9001"
)
CAPTURE_DISCLAIMER_HTML = (
    "<b>Tested only with DWARF 3</b> (" + TESTED_ENVIRONMENT + "). "
    "DWARF 2 and DWARF mini use the same capture code but have not been tested. "
    "DWARFLAB publishes no API and new firmware or app versions may change the "
    "behaviour. Use at your own risk and keep copies of your data; if something "
    "fails, please report it with the Technical log."
)


class CaptureOptionsWidget(QGroupBox):
    """Capture options added for DWARF 3 + NINA (continuous session, cleanup)."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__("Capture options", parent)
        form = _compact_form()

        self.compatibility_label = QLabel(CAPTURE_DISCLAIMER_HTML)
        self.compatibility_label.setWordWrap(True)
        self.compatibility_label.setStyleSheet(
            "QLabel { background: #fff4ce; color: #5c4400; padding: 8px; "
            "border: 1px solid #e0c060; border-radius: 4px; }"
        )

        self.continuous_info_label = QLabel(
            "The DWARF always captures in a continuous session, stacking on the "
            "telescope. dwarfAlp keeps that session running while exposure, gain, "
            "filter and binning stay the same, and hands the FITS to NINA in order. "
            "Frames NINA does not ask for stay on the DWARF."
        )
        self.continuous_info_label.setWordWrap(True)
        for label in (self.compatibility_label, self.continuous_info_label):
            # Wrapped labels spanning a QFormLayout row get a too small height
            # (the disclaimer was cut after two lines); a plain vertical layout
            # sizes them correctly.
            label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        self.continuous_idle_spin = QSpinBox()
        self.continuous_idle_spin.setRange(10, 3600)
        self.continuous_idle_spin.setSuffix(" s")
        self.continuous_idle_spin.setToolTip(
            "Stop the continuous session after this long without a new exposure."
        )
        self.continuous_max_frames_spin = QSpinBox()
        self.continuous_max_frames_spin.setRange(2, 9999)
        self.continuous_max_frames_spin.setToolTip(
            "Frame count requested from the DWARF for a continuous session."
        )
        self.delete_session_checkbox = QCheckBox("Delete DWARF session after download")
        self.delete_session_checkbox.setToolTip(
            "Removes the session folder (raw FITS, stacked image, previews) from the telescope."
        )
        self.delete_timeout_spin = QSpinBox()
        self.delete_timeout_spin.setRange(30, 1800)
        self.delete_timeout_spin.setSuffix(" s")
        self.delete_timeout_spin.setToolTip(
            "How long to wait for the DWARF to close the session before skipping deletion."
        )
        self.ready_timeout_spin = QSpinBox()
        self.ready_timeout_spin.setRange(30, 1800)
        self.ready_timeout_spin.setSuffix(" s")
        self.ready_timeout_spin.setToolTip(
            "How long a new capture waits for the DWARF to close the previous session."
        )

        self.autofocus_checkbox = QCheckBox("Autofocus before GOTO and calibration")
        self.autofocus_checkbox.setToolTip(
            "DWARF 3 firmware V1.5.4.1 accepts the command but never starts autofocus; "
            "each GOTO then waits 20 s for nothing. Focus in the DWARFLAB app instead."
        )
        self.autofocus_checkbox.setContentsMargins(24, 0, 0, 0)
        self.ring_light_checkbox = QCheckBox("Ring light off")
        self.battery_indicator_checkbox = QCheckBox("Battery indicator off")
        for box in (self.ring_light_checkbox, self.battery_indicator_checkbox):
            box.setToolTip(
                "Turned off when dwarfAlp connects to the DWARF; the DWARFLAB app can "
                "turn it on again."
            )
        self.battery_indicator_checkbox.setContentsMargins(24, 0, 0, 0)

        for spin in (self.continuous_idle_spin, self.delete_timeout_spin, self.ready_timeout_spin):
            spin.setFixedWidth(100)
        self.continuous_max_frames_spin.setFixedWidth(90)
        form.addRow(
            "Continuous idle timeout",
            _inline_row(self.continuous_idle_spin, "Max frames", self.continuous_max_frames_spin),
        )
        form.addRow(
            "Wait for DWARF ready", _inline_row(self.ready_timeout_spin, self.autofocus_checkbox)
        )
        form.addRow(
            _inline_row(self.delete_session_checkbox, "Deletion wait", self.delete_timeout_spin)
        )
        form.addRow(
            "DWARF lights",
            _inline_row(self.ring_light_checkbox, self.battery_indicator_checkbox),
        )
        self.delete_session_checkbox.toggled.connect(self._sync_state)
        layout = QVBoxLayout()
        layout.addWidget(self.compatibility_label)
        layout.addWidget(self.continuous_info_label)
        layout.addLayout(form)
        self.setLayout(layout)

    def _sync_state(self) -> None:
        self.delete_timeout_spin.setEnabled(self.delete_session_checkbox.isChecked())

    def populate(self, settings: Settings) -> None:
        self.continuous_idle_spin.setValue(
            int(round(settings.continuous_astro_idle_timeout_seconds))
        )
        self.continuous_max_frames_spin.setValue(int(settings.continuous_astro_max_frames))
        self.delete_session_checkbox.setChecked(settings.delete_astro_session_after_download)
        self.delete_timeout_spin.setValue(
            int(round(settings.delete_astro_session_timeout_seconds))
        )
        self.ready_timeout_spin.setValue(
            int(round(settings.astro_capture_ready_timeout_seconds))
        )
        self.autofocus_checkbox.setChecked(settings.autofocus_before_calibration)
        self.ring_light_checkbox.setChecked(settings.ring_light_off)
        self.battery_indicator_checkbox.setChecked(settings.battery_indicator_off)
        self._sync_state()

    def apply(self, settings: Settings) -> Settings:
        return settings.model_copy(
            update={
                # Always on in the GUI, even if an older profile saved it as false.
                "continuous_astro_session": True,
                "continuous_astro_idle_timeout_seconds": float(
                    self.continuous_idle_spin.value()
                ),
                "continuous_astro_max_frames": self.continuous_max_frames_spin.value(),
                "delete_astro_session_after_download": (
                    self.delete_session_checkbox.isChecked()
                ),
                "delete_astro_session_timeout_seconds": float(
                    self.delete_timeout_spin.value()
                ),
                "astro_capture_ready_timeout_seconds": float(
                    self.ready_timeout_spin.value()
                ),
                "autofocus_before_calibration": self.autofocus_checkbox.isChecked(),
                "ring_light_off": self.ring_light_checkbox.isChecked(),
                "battery_indicator_off": self.battery_indicator_checkbox.isChecked(),
            }
        )


DEFAULT_PROFILE_NAME = "dwarf-alpaca.yaml"

# Settings written by File > Save settings profile: everything editable on the
# Settings tab. Keys present in a loaded profile take precedence over values
# remembered from provisioning (IP, model, location, timezone).
PROFILE_KEYS: tuple[str, ...] = (
    "http_host",
    "http_port",
    "dwarf_ap_ip",
    "dwarf_device_model",
    "dwarf_ws_client_id",
    "force_simulation",
    "calibrate_after_server_start",
    "autofocus_before_calibration",
    "ring_light_off",
    "battery_indicator_off",
    "site_latitude",
    "site_longitude",
    "timezone_name",
    "continuous_astro_idle_timeout_seconds",
    "continuous_astro_max_frames",
    "delete_astro_session_after_download",
    "delete_astro_session_timeout_seconds",
    "astro_capture_ready_timeout_seconds",
)


def default_profile_path() -> Path:
    """Profile loaded at start-up: next to the executable, or the working folder."""

    if getattr(sys, "frozen", False):
        base = Path(sys.executable).resolve().parent
    else:
        base = Path.cwd()
    return base / DEFAULT_PROFILE_NAME


def profile_data(settings: Settings) -> dict:
    data = settings.model_dump(mode="json")
    return {key: data.get(key) for key in PROFILE_KEYS}


def write_profile(path: Path, settings: Settings) -> None:
    header = (
        "# dwarfAlp settings profile\n"
        "# Saved from File > Save settings profile. Loaded automatically at start-up\n"
        f"# when named {DEFAULT_PROFILE_NAME} next to the app. Values here override .env.\n"
    )
    body = yaml.safe_dump(profile_data(settings), sort_keys=False, allow_unicode=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(header + body, encoding="utf-8")
    tmp.replace(path)


def read_profile_keys(path: Path) -> set[str]:
    with path.open("r", encoding="utf-8") as stream:
        data = yaml.safe_load(stream) or {}
    if not isinstance(data, dict):
        raise ValueError("Settings profile must be a YAML mapping")
    return {str(key) for key in data}


class MainWindow(QMainWindow):
    def __init__(self, *, app_icon: Optional[QIcon] = None) -> None:
        super().__init__()
        self.setWindowTitle(f"DWARF Alpaca Control Center v{__version__}")
        self.resize(1024, 720)
        if app_icon and not app_icon.isNull():
            self.setWindowIcon(app_icon)

        self._settings_path: Optional[Path] = None
        self._profile_keys: set[str] = set()
        self._settings: Optional[Settings] = None
        self._state_store: Optional[StateStore] = None
        self._workers: set[AsyncWorker] = set()

        self.server_service = ServerService()
        self.server_service.status_changed.connect(self._handle_server_status)
        self.server_service.error_occurred.connect(self._handle_server_error)

        self.log_console = LogConsole()
        self.log_handler = QtLogHandler()
        self.log_handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
        self.log_handler.emitter.message.connect(self.log_console.append_message)
        logging.getLogger().addHandler(self.log_handler)

        self.activity_translator = ActivityTranslator()
        self.activity_console = ActivityConsole()
        self.activity_status_label = QLabel()
        self.activity_status_label.setWordWrap(True)
        self.activity_status_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.activity_status_label.setStyleSheet(
            "QLabel { font-weight: bold; padding: 4px 6px; background: #eef3f8; "
            "border: 1px solid #c8d4e0; border-radius: 3px; }"
        )
        self.activity_handler = ActivityLogHandler()
        self.activity_handler.emitter.record.connect(self._handle_activity_record)
        logging.getLogger().addHandler(self.activity_handler)
        logging.getLogger().setLevel(logging.INFO)

        self.settings_widget = SettingsOverridesWidget()
        self.capture_widget = CaptureOptionsWidget()
        self.provisioning_widget = ProvisioningWidget()
        self.server_widget = ServerControlWidget()
        self._connectivity_summary: str = ""
        self._saved_credentials: OrderedDict[str, str] = OrderedDict()
        self._latest_state: Optional[ConnectivityState] = None
        self._discovered_device_models: dict[str, str] = {}
        self._pending_start: Optional[tuple[Settings, bool]] = None
        self._server_status_message: str = "Stopped"

        self.provisioning_widget.provision_requested.connect(self._handle_provision)
        self.provisioning_widget.discovery_requested.connect(self._handle_discover)
        self.provisioning_widget.wifi_scan_requested.connect(self._handle_wifi_scan)
        self.provisioning_widget.device_selected.connect(self._on_device_selected)
        self.server_widget.start_requested.connect(self._handle_start_server)
        self.server_widget.stop_requested.connect(self._handle_stop_server)
        self.settings_widget.location_fetch_requested.connect(self._handle_location_fetch)

        content = QWidget()
        content_layout = QVBoxLayout(content)

        splitter = QSplitter(Qt.Vertical)
        upper = QWidget()
        upper_layout = QHBoxLayout(upper)
        tabs = QTabWidget()
        tabs.addTab(self.server_widget, "Server")
        tabs.addTab(self.provisioning_widget, "Provisioning")
        tabs.addTab(self.settings_widget, "Settings")
        capture_page = QWidget()
        capture_layout = QVBoxLayout(capture_page)
        capture_layout.addWidget(self.capture_widget)
        capture_layout.addStretch(1)
        tabs.addTab(capture_page, "Capture")
        upper_layout.addWidget(tabs, 2)
        self.help_panel = QLabel()
        self.help_panel.setWordWrap(True)
        self.help_panel.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.help_panel.setMargin(12)
        self.help_panel.setFrameStyle(QFrame.Panel | QFrame.Sunken)
        help_scroll = QScrollArea()
        help_scroll.setWidgetResizable(True)
        help_scroll.setFrameShape(QFrame.NoFrame)
        help_scroll.setWidget(self.help_panel)
        upper_layout.addWidget(help_scroll, 1)
        upper_layout.setContentsMargins(0, 0, 0, 0)
        splitter.addWidget(upper)
        log_panel = QWidget()
        log_layout = QVBoxLayout(log_panel)
        log_layout.setContentsMargins(0, 0, 0, 0)
        log_layout.addWidget(self.activity_status_label)
        self.log_tabs = QTabWidget()
        self.log_tabs.addTab(self.activity_console, "Activity")
        self.log_tabs.addTab(self.log_console, "Technical")
        log_layout.addWidget(self.log_tabs)
        self._refresh_activity_status()
        splitter.addWidget(log_panel)
        # The tabs only take the height they need; the logs get the rest.
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        self._splitter = splitter
        self._upper_area = upper
        self._splitter_placed = False
        content_layout.addWidget(splitter)
        self.setCentralWidget(content)

        self._create_menu()
        self._tabs = tabs
        startup_profile = default_profile_path()
        self._load_settings(startup_profile if startup_profile.exists() else None)
        self._help_messages = {
            0: (
                "Server",
                "<b>Server tab</b><br/>Start or stop the Alpaca service, manage preflight checks,"
                " and monitor server status messages.",
            ),
            1: (
                "Provisioning",
                "<b>Provisioning tab</b><br/>Discover DWARF units over BLE, fetch Wi-Fi networks,"
                " and provision STA credentials. Select a device, pick a network,"
                " and provide SSID/password plus optional BLE password overrides.",
            ),
            2: (
                "Settings",
                "<b>Settings tab</b><br/>Override server host/port, DWARF IP, and websocket client ID."
                " Choose the correct DWARF model (DWARF 3, DWARF 2, or DWARF mini)"
                " and enter or fetch observer coordinates before optional post-start calibration.",
            ),
            3: (
                "Capture",
                "<b>Capture tab</b><br/>Options that make the DWARF work the way NINA"
                " expects."
                "<br/><br/><b>Continuous DWARF session</b>: the DWARF always"
                " captures as a stacking session on the telescope; one session serves a"
                " whole sequence instead of one per frame (closing a session takes about"
                " a minute). It ends when exposure, gain, filter or binning change, on"
                " abort, slew, tracking off, focuser move, disconnect, or after the idle"
                " timeout."
                " NINA receives the frames in order, oldest first, and exactly as many as"
                " it asks for; when the Wi-Fi download is slower than the exposures the"
                " DWARF takes more, which stay on the telescope (Activity reports them)."
                "<br/><br/><b>Delete DWARF session after download</b>: removes the session"
                " folder (raw FITS, stacked image, previews) from the telescope once the"
                " DWARF has closed it. Keep the app open for a minute or two after the"
                " sequence so the deletion can finish."
                "<br/><br/><b>Wait for DWARF ready</b>: how long a new capture waits for"
                " the previous session to close."
                "<br/><br/><b>Autofocus before GOTO and calibration</b>: off by default."
                " The tested DWARF 3 firmware accepts the command but never starts"
                " autofocus, so each GOTO waited 20 s for nothing. Focus in the DWARFLAB"
                " app before connecting NINA."
                "<br/><br/><b>DWARF lights</b>: turn the ring light and the battery"
                " indicator off when dwarfAlp connects (start the server again after a"
                " change). They stay off; the DWARFLAB app can turn them on again.",
            ),
        }
        self._refresh_state()
        _configure_start_logging(self._settings)
        self._tabs.currentChanged.connect(self._update_help)
        self._update_help(self._tabs.currentIndex())
        # Numbers are typed; stepping arrows only moved them one unit at a time.
        for spin in self.findChildren(QAbstractSpinBox):
            spin.setButtonSymbols(QAbstractSpinBox.NoButtons)

    # region menu and lifecycle
    def _create_menu(self) -> None:
        menu = self.menuBar().addMenu("File")
        load_action = QAction("Load settings profile…", self)
        load_action.triggered.connect(self._choose_settings_file)
        menu.addAction(load_action)

        save_action = QAction("Save settings profile", self)
        save_action.setShortcut(QKeySequence.Save)
        save_action.triggered.connect(self._save_settings_profile)
        menu.addAction(save_action)

        save_as_action = QAction("Save settings profile as…", self)
        save_as_action.triggered.connect(self._save_settings_profile_as)
        menu.addAction(save_as_action)

        reload_action = QAction("Reload", self)
        reload_action.triggered.connect(lambda: self._load_settings(self._settings_path))
        menu.addAction(reload_action)

        help_menu = self.menuBar().addMenu("Help")
        about_action = QAction("About dwarfAlp", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            "About dwarfAlp",
            (
                "<h3>dwarfAlp</h3>"
                f"<p>Version {__version__}</p>"
                "<p>ASCOM Alpaca bridge for DWARFLAB smart telescopes.</p>"
                "<p>Licensed under the GNU General Public License v3.0.</p>"
            ),
        )

    def _choose_settings_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select settings YAML",
            str(self._settings_path.parent if self._settings_path else Path.cwd()),
            "YAML files (*.yaml *.yml)",
        )
        if path:
            self._load_settings(Path(path))

    def _save_settings_profile(self) -> None:
        self._write_settings_profile(self._settings_path or default_profile_path())

    def _save_settings_profile_as(self) -> None:
        start = self._settings_path or default_profile_path()
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save settings profile",
            str(start),
            "YAML files (*.yaml *.yml)",
        )
        if path:
            self._write_settings_profile(Path(path))

    def _write_settings_profile(self, path: Path) -> None:
        try:
            settings = self.capture_widget.apply(
                self.settings_widget.apply(self._current_settings())
            )
            write_profile(path, settings)
        except Exception as exc:
            QMessageBox.critical(self, "Settings", f"Failed to save settings profile: {exc}")
            return
        self._settings = settings
        self._settings_path = path
        self._profile_keys = set(PROFILE_KEYS)
        self.statusBar().showMessage(f"Saved settings profile to {path}", 5000)
        logging.getLogger(__name__).info("gui.settings_profile_saved path=%s", path)

    def _load_settings(self, path: Optional[Path]) -> None:
        try:
            settings = load_settings(str(path) if path else None)
            profile_keys = read_profile_keys(path) if path else set()
        except Exception as exc:
            QMessageBox.critical(self, "Settings", f"Failed to load settings: {exc}")
            return
        self._profile_keys = profile_keys
        resolved_state_dir = _resolve_state_directory(settings.state_directory)
        if resolved_state_dir != settings.state_directory:
            settings = settings.model_copy(update={"state_directory": resolved_state_dir})
        resolved_state_dir.mkdir(parents=True, exist_ok=True)
        self._settings_path = path
        self._settings = settings
        self._state_store = create_state_store(settings.state_directory)
        self.settings_widget.populate(settings)
        self.capture_widget.populate(settings)
        self.provisioning_widget.set_ble_password(settings.ble_password or "DWARF_12345678")
        self.statusBar().showMessage(
            f"Loaded settings from {path}" if path else "Loaded default environment settings",
            5000,
        )

    def _current_settings(self) -> Settings:
        if not self._settings:
            self._settings = load_settings(
                str(self._settings_path) if self._settings_path else None
            )
        return self._settings

    def _handle_activity_record(self, message: str, created: float) -> None:
        for entry in self.activity_translator.feed(message, created):
            self.activity_console.append_entry(entry)
        self._refresh_activity_status()

    def _refresh_activity_status(self) -> None:
        self.activity_status_label.setText(self.activity_translator.status.render())

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        if not self._splitter_placed:
            self._splitter_placed = True
            QTimer.singleShot(0, self._place_splitter)

    def _place_splitter(self) -> None:
        """Put the divider right below the tallest tab page.

        One divider is shared by all tabs. Qt over-estimates the minimum
        height of wrapped labels (it measures them at a narrow width), which
        left an empty band under the Capture tab; each page is measured at
        its real width instead.
        """

        upper = self._measure_upper_area()
        if upper is None:
            return
        total = max(self._splitter.height(), upper + 200)
        self._splitter.setSizes([upper, total - upper])

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        if self._splitter_placed:
            # A narrower window wraps the labels into more lines.
            QTimer.singleShot(0, self._measure_upper_area)

    def _measure_upper_area(self) -> int | None:
        """Set each page's minimum height for its real width; return the tab area height."""

        current = self._tabs.currentWidget()
        if current is None:
            return None
        width = max(current.width(), 1)
        needed = 0
        for i in range(self._tabs.count()):
            page = self._tabs.widget(i)
            height = page.minimumSizeHint().height()
            if page.hasHeightForWidth():
                for_width = page.heightForWidth(width)
                if for_width > 0:
                    height = min(height, for_width)
            # Overrides the over-estimate, so the divider can sit right there.
            page.setMinimumHeight(height)
            needed = max(needed, height)
        chrome = max(self._tabs.height() - current.height(), 0)
        return max(needed + chrome, 1)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self.log_handler.emitter.message.disconnect(self.log_console.append_message)
        logging.getLogger().removeHandler(self.log_handler)
        self.activity_handler.emitter.record.disconnect(self._handle_activity_record)
        logging.getLogger().removeHandler(self.activity_handler)
        if self.server_service.is_running():
            self.server_service.stop()
        super().closeEvent(event)

    # endregion

    # region state display
    def _refresh_state(self) -> None:
        settings = self._current_settings()
        store = self._state_store
        if store is None:
            store = create_state_store(settings.state_directory)
            self._state_store = store
        state = store.load()
        self._latest_state = state
        current_settings = self._current_settings()
        updated_settings = current_settings

        profile = self._profile_keys
        tz_name = state.timezone_name
        if "timezone_name" not in profile:
            if tz_name != updated_settings.timezone_name:
                updated_settings = updated_settings.with_timezone_name(tz_name)
            self.settings_widget.set_timezone_name(tz_name)

        if (
            state.site_latitude is not None
            and state.site_longitude is not None
            and not {"site_latitude", "site_longitude"} & profile
        ):
            if (
                updated_settings.site_latitude != state.site_latitude
                or updated_settings.site_longitude != state.site_longitude
            ):
                updated_settings = updated_settings.model_copy(
                    update={
                        "site_latitude": state.site_latitude,
                        "site_longitude": state.site_longitude,
                    }
                )
            self.settings_widget.set_site_location(
                state.site_latitude, state.site_longitude
            )

        if state.device_model and "dwarf_device_model" not in profile:
            model = normalize_dwarf_device_model(state.device_model)
            client_id = _MODEL_DEFAULT_CLIENT_ID[model]
            if (
                updated_settings.dwarf_device_model != model
                or updated_settings.dwarf_ws_client_id != client_id
            ):
                updated_settings = updated_settings.model_copy(
                    update={
                        "dwarf_device_model": model,
                        "dwarf_ws_client_id": client_id,
                    }
                )
            self.settings_widget.set_device_model(model)

        if state.sta_ip and "dwarf_ap_ip" not in profile:
            if updated_settings.dwarf_ap_ip != state.sta_ip:
                updated_settings = updated_settings.model_copy(
                    update={"dwarf_ap_ip": state.sta_ip, "network_mode": "sta"}
                )
            self.settings_widget.dwarf_ip_edit.setText(state.sta_ip)

        if updated_settings is not current_settings:
            self._settings = updated_settings
        summary = self._format_state_summary(state)
        self._connectivity_summary = summary
        self._saved_credentials = OrderedDict(state.wifi_credentials.items())
        ssid, password = self._get_last_saved_credentials()
        self.provisioning_widget.populate_saved_credentials(ssid, password)
        self.provisioning_widget.set_device_address(state.last_device_address)
        self._update_help(self._tabs.currentIndex())

    @staticmethod
    def _format_state_summary(state: ConnectivityState) -> str:
        parts = ["<b>Connectivity state</b>"]
        parts.append(f"Mode: {state.mode}")
        parts.append(f"STA IP: {state.sta_ip or 'unknown'}")
        if state.last_error:
            parts.append(f"Last error: {state.last_error}")
        if state.last_device_address:
            parts.append(f"Last device: {state.last_device_address}")
        if state.device_model:
            parts.append(f"Device model: {state.device_model}")
        if state.wifi_credentials:
            networks = ", ".join(state.wifi_credentials.keys())
            parts.append(f"Saved networks: {networks}")
        if state.timezone_name:
            parts.append(f"Timezone name: {state.timezone_name}")
        if state.site_latitude is not None and state.site_longitude is not None:
            parts.append(
                f"Site: {state.site_latitude:.6f}, {state.site_longitude:.6f}"
            )
        return "<br/>".join(parts)

    def _get_last_saved_credentials(self) -> tuple[Optional[str], Optional[str]]:
        if not self._saved_credentials:
            return (None, None)
        ssid, password = next(reversed(self._saved_credentials.items()))
        return ssid, password

    def _update_help(self, index: int) -> None:
        title, body = self._help_messages.get(index, ("", ""))
        sections: list[str] = []
        if index == 0:
            sections.append(
                f"<b>Server status</b><br/>Current state: {self._server_status_message}."
            )
        if index == 1 and self._connectivity_summary:
            sections.append(self._connectivity_summary)

        fragments: list[str] = []
        if title:
            fragments.append(f"<h3>{title}</h3>")
        if body:
            fragments.append(f"<p>{body}</p>")
        for section in sections:
            fragments.append(f"<p>{section}</p>")

        self.help_panel.setText("".join(fragments) or "")

    # endregion

    # region worker helpers
    def _start_worker(self, worker: AsyncWorker) -> None:
        self._workers.add(worker)
        worker.finished_success.connect(lambda _: self._workers.discard(worker))
        worker.finished_error.connect(lambda _: self._workers.discard(worker))
        worker.start()

    def _handle_worker_error(self, exc: Exception, context: str) -> None:
        logger.error("gui.worker.failure", context=context, error=str(exc))
        QMessageBox.critical(self, "Error", f"{context}: {exc}")

    # endregion

    # region provisioning
    def _on_device_selected(self, address: str) -> None:
        normalized = address.strip()
        if not normalized:
            return
        store = self._state_store
        if store is None:
            store = create_state_store(self._current_settings().state_directory)
            self._state_store = store
        state = self._latest_state or store.load()
        state.last_device_address = normalized
        detected_model = self._discovered_device_models.get(normalized)
        if detected_model:
            state.device_model = detected_model
            client_id = _MODEL_DEFAULT_CLIENT_ID[detected_model]
            self._settings = self._current_settings().model_copy(
                update={
                    "dwarf_device_model": detected_model,
                    "dwarf_ws_client_id": client_id,
                }
            )
            self.settings_widget.set_device_model(detected_model)
        self._latest_state = state
        store.save(state)

    def _build_provisioning_payload(self) -> Optional[dict[str, Optional[str]]]:
        payload = self.provisioning_widget.current_payload()
        ssid = payload.get("ssid", "").strip()
        password = payload.get("password", "") or ""
        if not ssid or not password:
            saved_ssid, saved_password = self._get_last_saved_credentials()
            if saved_ssid and not ssid:
                payload["ssid"] = saved_ssid
                self.provisioning_widget.ssid_edit.setText(saved_ssid)
                ssid = saved_ssid
            if saved_password and not password:
                payload["password"] = saved_password
                self.provisioning_widget.password_edit.setText(saved_password)
                password = saved_password or ""
        if ssid and password:
            payload["ssid"] = ssid
            payload["password"] = password
            return payload
        return None

    def _continue_start_after_provision(self) -> None:
        if not self._pending_start:
            return
        settings, skip_preflight = self._pending_start
        if not skip_preflight and not settings.force_simulation:
            timeout = self.settings_widget.preflight_timeout_spin.value()
            interval = self.settings_widget.preflight_interval_spin.value()
            worker = AsyncWorker(
                lambda: _preflight_session(settings, timeout=timeout, interval=interval)
            )
            worker.finished_success.connect(lambda _: self._launch_server(settings))
            worker.finished_error.connect(self._on_preflight_error)
            self.server_widget.set_busy("Preflight in progress…")
            self._start_worker(worker)
        else:
            self._launch_server(settings)

    def _on_prestart_provision_success(self, _: object) -> None:
        self.provisioning_widget.show_status("Provisioning succeeded")
        # A freshly provisioned STA address replaces the IP from the profile.
        self._profile_keys.discard("dwarf_ap_ip")
        self._refresh_state()
        self._continue_start_after_provision()

    def _on_prestart_provision_error(self, exc: Exception) -> None:
        self._pending_start = None
        self.provisioning_widget.show_status(f"Provisioning failed: {exc}")
        self.server_widget.set_running(False, "Stopped")
        self._handle_worker_error(exc, "Provisioning before start failed")

    def _on_preflight_error(self, exc: Exception) -> None:
        self._pending_start = None
        self.server_widget.set_running(False, "Stopped")
        self._handle_worker_error(exc, "Preflight failed")

    def _handle_discover(self, payload: dict) -> None:
        worker = AsyncWorker(lambda: self._discover_devices(payload))
        worker.finished_success.connect(self._on_discover_success)
        worker.finished_error.connect(
            lambda exc: self._handle_worker_error(exc, "Discovery failed")
        )
        self.provisioning_widget.show_status("Scanning for DWARF devices…")
        self._start_worker(worker)

    async def _discover_devices(self, payload: dict) -> list[tuple[str, str]]:
        settings = self._current_settings()
        adapter = settings.ble_adapter
        provisioner = DwarfBleProvisioner()
        devices = await provisioner.discover_devices(adapter=adapter)  # type: ignore[arg-type]
        return [(device.name or "<unnamed>", getattr(device, "address", "")) for device in devices]

    def _on_discover_success(self, result: object) -> None:
        if not isinstance(result, list):
            return
        devices = [(name, address) for name, address in result if isinstance(name, str)]
        self._discovered_device_models = {
            address: model
            for name, address in devices
            if address and (model := _infer_dwarf_model_from_name(name)) is not None
        }
        self.provisioning_widget.populate_devices(devices)
        self.provisioning_widget.show_status(f"Found {len(devices)} device(s)")

    def _handle_wifi_scan(self, payload: dict) -> None:
        worker = AsyncWorker(lambda: self._scan_wifi(payload))
        worker.finished_success.connect(self._on_wifi_success)
        worker.finished_error.connect(self._on_wifi_error)
        self.provisioning_widget.show_status("Fetching Wi-Fi list…")
        self._start_worker(worker)

    async def _scan_wifi(self, payload: dict) -> list[str]:
        ble_password = payload.get("ble_password")
        device = payload.get("device_address")
        settings = self._current_settings()
        resolved_ble_password = ble_password or settings.ble_password or "DWARF_12345678"
        provisioner = DwarfBleProvisioner()
        try:
            networks = await provisioner.fetch_wifi_list(
                device=device if device else None,
                adapter=settings.ble_adapter,
                ble_password=resolved_ble_password,
                timeout=settings.provisioning_timeout_seconds,
            )
        except ProvisioningError:
            raise
        except Exception as exc:  # pragma: no cover - hardware dependent
            raise ProvisioningError(f"Unexpected Wi-Fi scan error: {exc}") from exc
        return networks

    def _on_wifi_success(self, result: object) -> None:
        if not isinstance(result, list):
            return
        networks = [ssid for ssid in result if isinstance(ssid, str)]
        self.provisioning_widget.populate_wifi(networks)
        message = (
            "No Wi-Fi networks reported"
            if not networks
            else f"Retrieved {len(networks)} network(s)"
        )
        self.provisioning_widget.show_status(message)

    def _on_wifi_error(self, exc: Exception) -> None:
        self.provisioning_widget.show_status(f"Wi-Fi scan failed: {exc}")
        self._handle_worker_error(exc, "Wi-Fi scan failed")

    def _handle_provision(self, payload: dict) -> None:
        if not str(payload.get("device_address") or "").strip():
            self.provisioning_widget.show_status(
                "Select a discovered DWARF device before provisioning Wi-Fi"
            )
            return
        if not str(payload.get("ssid") or "").strip():
            self.provisioning_widget.show_status(
                "Select or enter a Wi-Fi network before provisioning"
            )
            return
        if not str(payload.get("password") or ""):
            self.provisioning_widget.show_status(
                "Enter the Wi-Fi password before provisioning"
            )
            return
        worker = AsyncWorker(lambda: self._provision(payload))
        worker.finished_success.connect(lambda _: self._on_provision_success())
        worker.finished_error.connect(self._on_provision_error)
        self.provisioning_widget.show_status("Provisioning in progress…")
        self._start_worker(worker)

    async def _provision(self, payload: dict) -> None:
        settings = self._current_settings()
        await provision_sta(
            settings=settings,
            ssid=payload.get("ssid", ""),
            password=payload.get("password", ""),
            adapter=settings.ble_adapter,
            ble_password=payload.get("ble_password"),
            device_address=payload.get("device_address"),
        )

    def _on_provision_success(self) -> None:
        self.provisioning_widget.show_status("Provisioning succeeded")
        # A freshly provisioned STA address replaces the IP from the profile.
        self._profile_keys.discard("dwarf_ap_ip")
        self._refresh_state()

    def _on_provision_error(self, exc: Exception) -> None:
        self.provisioning_widget.show_status(f"Provisioning failed: {exc}")
        self._handle_worker_error(exc, "Provisioning failed")

    # endregion

    # region observer location
    def _handle_location_fetch(self) -> None:
        worker = AsyncWorker(self._fetch_current_location)
        worker.finished_success.connect(self._on_location_fetch_success)
        worker.finished_error.connect(self._on_location_fetch_error)
        self.settings_widget.set_location_lookup_busy(
            True, "Estimating position from public IP..."
        )
        self._start_worker(worker)

    async def _fetch_current_location(self) -> tuple[float, float, str]:
        settings = self._current_settings()
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            response = await client.get(settings.geolocation_lookup_url)
            response.raise_for_status()
            payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("Location service returned an invalid response")
        if payload.get("success") is False:
            reason = payload.get("message") or payload.get("reason") or "lookup failed"
            raise RuntimeError(f"Location service: {reason}")
        try:
            latitude = float(payload["latitude"])
            longitude = float(payload["longitude"])
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError("Location service did not return coordinates") from exc
        if not -90.0 <= latitude <= 90.0 or not -180.0 <= longitude <= 180.0:
            raise RuntimeError("Location service returned coordinates outside the valid range")
        description_parts = [
            str(value).strip()
            for value in (payload.get("city"), payload.get("region"), payload.get("country"))
            if value
        ]
        return (latitude, longitude, ", ".join(description_parts))

    def _on_location_fetch_success(self, result: object) -> None:
        if not isinstance(result, tuple) or len(result) != 3:
            self._on_location_fetch_error(RuntimeError("Unexpected location result"))
            return
        latitude, longitude, description = result
        self.settings_widget.set_site_location(float(latitude), float(longitude))
        suffix = f" ({description})" if description else ""
        self.settings_widget.set_location_lookup_busy(
            False,
            f"Estimated {float(latitude):.6f}, {float(longitude):.6f}{suffix}. Verify before use.",
        )

    def _on_location_fetch_error(self, exc: Exception) -> None:
        self.settings_widget.set_location_lookup_busy(False, f"Lookup failed: {exc}")
        self._handle_worker_error(exc, "Current-position lookup failed")

    # endregion

    # region server control
    def _handle_start_server(self) -> None:
        if self.server_service.is_running():
            QMessageBox.information(self, "Server", "Server is already running")
            return
        try:
            settings = self._build_settings_for_server()
        except ValueError as exc:
            QMessageBox.warning(self, "Observer location", str(exc))
            return
        if settings.calibrate_after_server_start and (
            settings.site_latitude is None
            or settings.site_longitude is None
            or (settings.site_latitude == 0.0 and settings.site_longitude == 0.0)
        ):
            QMessageBox.warning(
                self,
                "Observer location required",
                "Enter site latitude and longitude or fetch the current position before "
                "starting the server with calibration enabled.",
            )
            return
        # Seed the Activity status before the connectivity preflight so its
        # messages can name the DWARF and its IP.
        self.activity_translator.configure(
            model=normalize_dwarf_device_model(settings.dwarf_device_model),
            ip=settings.dwarf_ap_ip,
        )
        self._refresh_activity_status()
        skip_preflight = self.settings_widget.skip_preflight_checkbox.isChecked()
        self._pending_start = (settings, skip_preflight)
        # Starting against an already reachable STA/AP address must not trigger
        # BLE provisioning. Provisioning is an explicit action on its own tab.
        self._continue_start_after_provision()

    def _build_settings_for_server(self) -> Settings:
        base = self._current_settings()
        override = self.capture_widget.apply(self.settings_widget.apply(base))
        entered_ip = self.settings_widget.dwarf_ip_edit.text().strip()
        ip_is_manual_override = bool(entered_ip and entered_ip != base.dwarf_ap_ip)
        store = self._state_store
        if store is None:
            store = create_state_store(override.state_directory)
            self._state_store = store
        state = self._latest_state
        if state is None:
            state = store.load()
            self._latest_state = state

        if state:
            detected_mode = (state.mode or "").lower()
            if detected_mode in ("", "unknown"):
                detected_mode = "sta" if state.sta_ip else "ap"
            override.network_mode = detected_mode
            if (
                state.sta_ip
                and not ip_is_manual_override
                and "dwarf_ap_ip" not in self._profile_keys
            ):
                override.dwarf_ap_ip = state.sta_ip
                self.settings_widget.dwarf_ip_edit.setText(state.sta_ip)
            needs_save = False
            normalized_name = (
                override.timezone_name.strip()
                if isinstance(override.timezone_name, str) and override.timezone_name.strip()
                else None
            )
            if normalized_name != state.timezone_name:
                state.timezone_name = normalized_name
                needs_save = True
            if (
                override.site_latitude != state.site_latitude
                or override.site_longitude != state.site_longitude
            ):
                state.site_latitude = override.site_latitude
                state.site_longitude = override.site_longitude
                needs_save = True
            if needs_save:
                store.save(state)
                self._latest_state = state
        if override != base:
            self._settings = override
        return override

    def _launch_server(self, settings: Settings) -> None:
        self.activity_translator.configure(
            model=normalize_dwarf_device_model(settings.dwarf_device_model),
            ip=settings.dwarf_ap_ip,
        )
        self._refresh_activity_status()
        try:
            self.server_service.start(settings)
        except Exception as exc:
            self._handle_worker_error(exc, "Unable to start server")
            self._pending_start = None
            return
        self._pending_start = None
        self.server_widget.set_running(True, "Starting…")

    def _handle_stop_server(self) -> None:
        if not self.server_service.is_running():
            return
        self.server_widget.set_busy("Stopping…")
        self.server_service.stop()

    def _handle_server_status(self, status: ServerStatus) -> None:
        self._server_status_message = status.message
        self.server_widget.set_running(status.running, status.message)
        if not status.running:
            for entry in self.activity_translator.server_stopped(time.time()):
                self.activity_console.append_entry(entry)
            self._refresh_activity_status()
        if status.running:
            self.server_widget.set_master_lock_status(status.has_master_lock)
            self.server_widget.set_battery_status(status.battery_percent)
            self.server_widget.set_calibration_status(
                status.calibration_status, status.calibration_detail
            )
        else:
            self.server_widget.set_master_lock_status(None)
            self.server_widget.set_battery_status(None)
            self.server_widget.set_calibration_status(None)
            self._refresh_state()
        self._update_help(self._tabs.currentIndex())

    def _handle_server_error(self, message: str) -> None:
        self._handle_worker_error(RuntimeError(message), "Server error")

    # endregion


def _apply_field_style(app: QApplication) -> None:
    """Give value fields a full visible border and a light shade.

    Qt's Windows 11 style draws input fields with an almost invisible border and
    only an underline; the classic Windows style draws a full frame. The shade
    comes from the palette, so native drawing (spin box arrows, combo arrows)
    is kept.
    """

    available = {name.lower() for name in QStyleFactory.keys()}
    if "windowsvista" in available:
        app.setStyle("windowsvista")
    elif "fusion" in available:
        app.setStyle("fusion")
    palette = app.palette()
    base = palette.color(QPalette.Base)
    if base.lightness() > 128:  # light theme: shade fields slightly
        palette.setColor(QPalette.Base, QColor("#eef3f8"))
        app.setPalette(palette)
        app.setStyleSheet(BUTTON_STYLE)


# Buttons stand out from the shaded value fields: blue-grey fill, darker
# border, and clear hover, pressed and disabled states.
BUTTON_STYLE = """
QPushButton {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #f4f8fc, stop:1 #d5e2ef);
    border: 1px solid #6f8fae;
    border-radius: 3px;
    padding: 4px 12px;
    color: #10283f;
}
QPushButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #eaf3fc, stop:1 #bcd4ec);
    border-color: #2f6ea5;
}
QPushButton:pressed {
    background: #a9c6e3;
    border-color: #2f6ea5;
}
QPushButton:focus {
    border-color: #2f6ea5;
}
QPushButton:disabled {
    background: #f0f0f0;
    border-color: #c4c4c4;
    color: #9a9a9a;
}
"""


def _close_bootloader_splash() -> None:
    """Close the PyInstaller splash shown while the .exe unpacks."""

    try:
        import pyi_splash  # type: ignore[import-not-found]
    except ImportError:
        return
    try:
        pyi_splash.close()
    except Exception:  # pragma: no cover - only in the frozen build
        pass


def _acquire_single_instance_lock() -> QLockFile | None:
    """Return the lock, or None if another copy of the program is running.

    On a slow computer the program takes a while to appear, and a second
    double-click started a second copy.
    """

    lock_dir = _resolve_state_directory(Path("var"))
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(lock_dir / "dwarf-alpaca-gui.lock"))
    lock.setStaleLockTime(0)
    if lock.tryLock(100):
        return lock
    return None


def main() -> None:
    import sys

    _configure_gui_structlog()
    app = QApplication(sys.argv)
    _apply_field_style(app)
    icon = _load_app_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)

    lock = _acquire_single_instance_lock()
    if lock is None:
        _close_bootloader_splash()
        QMessageBox.information(
            None,
            "DWARF Alpaca Control Center",
            "DWARF Alpaca Control Center is already running.",
        )
        sys.exit(0)

    splash: QSplashScreen | None = None
    if not getattr(sys, "frozen", False) and SPLASH_PATH.exists():
        # The frozen .exe shows the PyInstaller splash instead.
        splash = QSplashScreen(QPixmap(str(SPLASH_PATH)))
        splash.show()
        app.processEvents()

    window = MainWindow(app_icon=icon if not icon.isNull() else None)
    window.show()
    if splash is not None:
        splash.finish(window)
    _close_bootloader_splash()
    exit_code = app.exec()
    lock.unlock()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
