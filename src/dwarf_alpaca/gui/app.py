from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
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
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..config.settings import Settings, load_settings
from ..dwarf.ble_provisioner import DwarfBleProvisioner, ProvisioningError
from ..dwarf.state import ConnectivityState
from ..provisioning.workflow import create_state_store, provision_sta
from ..cli import _configure_start_logging, _preflight_session
from .logging import QtLogHandler
from .server import ServerService, ServerStatus
from .workers import AsyncWorker


logger = logging.getLogger(__name__)


APP_ICON_PATH = Path(__file__).resolve().parents[3] / "images" / "dwarfalplogo.ico"


WS_CLIENT_CHOICES: list[tuple[str, str]] = [
    ("DWARF 3", "0000DAF3-0000-1000-8000-00805F9B34FB"),
    ("DWARF 2", "0000DAF2-0000-1000-8000-00805F9B34FB"),
]


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


class SettingsOverridesWidget(QGroupBox):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__("Server Overrides", parent)
        form = QFormLayout()

        self.http_host_edit = QLineEdit()
        self.http_port_spin = QSpinBox()
        self.http_port_spin.setRange(1, 65535)
        self.dwarf_ip_edit = QLineEdit()
        self.ws_client_id_combo = QComboBox()
        self.ws_client_id_combo.setEditable(True)
        for label, value in WS_CLIENT_CHOICES:
            display = f"{label} ({value})"
            self.ws_client_id_combo.addItem(display, value)
        self.ws_client_id_combo.setInsertPolicy(QComboBox.NoInsert)
        self.force_sim_checkbox = QCheckBox("Force simulation mode")
        self.skip_preflight_checkbox = QCheckBox("Skip connectivity preflight")
        self.preflight_timeout_spin = QSpinBox()
        self.preflight_timeout_spin.setRange(5, 1800)
        self.preflight_timeout_spin.setSuffix(" s")
        self.preflight_interval_spin = QSpinBox()
        self.preflight_interval_spin.setRange(1, 120)
        self.preflight_interval_spin.setSuffix(" s")

        form.addRow("HTTP host", self.http_host_edit)
        form.addRow("HTTP port", self.http_port_spin)
        form.addRow("DWARF IP", self.dwarf_ip_edit)
        form.addRow("WS client ID", self.ws_client_id_combo)
        form.addRow(self.force_sim_checkbox)
        form.addRow(self.skip_preflight_checkbox)
        form.addRow("Preflight timeout", self.preflight_timeout_spin)
        form.addRow("Preflight interval", self.preflight_interval_spin)
        self.setLayout(form)

    def populate(self, settings: Settings) -> None:
        self.http_host_edit.setText(settings.http_host)
        self.http_port_spin.setValue(settings.http_port)
        self.dwarf_ip_edit.setText(settings.dwarf_ap_ip)
        index = self.ws_client_id_combo.findData(settings.dwarf_ws_client_id)
        if index >= 0:
            self.ws_client_id_combo.setCurrentIndex(index)
        else:
            self.ws_client_id_combo.setEditText(settings.dwarf_ws_client_id)
        self.force_sim_checkbox.setChecked(settings.force_simulation)
        self.skip_preflight_checkbox.setChecked(False)
        self.preflight_timeout_spin.setValue(180)
        self.preflight_interval_spin.setValue(5)

    def apply(self, settings: Settings) -> Settings:
        data = settings.model_dump()
        selected_client_id = self.ws_client_id_combo.currentData()
        if not isinstance(selected_client_id, str) or not selected_client_id.strip():
            selected_client_id = self.ws_client_id_combo.currentText().strip()
        selected_client_id = selected_client_id or settings.dwarf_ws_client_id
        data.update(
            {
                "http_host": self.http_host_edit.text().strip() or settings.http_host,
                "http_port": self.http_port_spin.value(),
                "dwarf_ap_ip": self.dwarf_ip_edit.text().strip() or settings.dwarf_ap_ip,
                "dwarf_ws_client_id": selected_client_id,
                "force_simulation": self.force_sim_checkbox.isChecked(),
            }
        )
        return settings.model_validate(data)


class ProvisioningWidget(QGroupBox):
    provision_requested = Signal(dict)
    discovery_requested = Signal(dict)
    wifi_scan_requested = Signal(dict)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__("Provisioning", parent)
        layout = QVBoxLayout()

        form = QFormLayout()
        self.ssid_edit = QLineEdit()
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.show_password_checkbox = QCheckBox("Show password")
        self.ble_password_edit = QLineEdit()
        self.device_address_edit = QLineEdit()

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

        self.setLayout(layout)

        self.start_button.clicked.connect(self.start_requested)
        self.stop_button.clicked.connect(self.stop_requested)

    def set_running(self, running: bool, message: str) -> None:
        self.status_label.setText(message)
        self.start_button.setEnabled(not running)
        self.stop_button.setEnabled(running)

    def set_busy(self, message: str) -> None:
        self.status_label.setText(message)
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(False)


def _load_app_icon() -> QIcon:
    if APP_ICON_PATH.exists():
        return QIcon(str(APP_ICON_PATH))
    logger.warning("gui.icon.missing", path=str(APP_ICON_PATH))
    return QIcon()


class MainWindow(QMainWindow):
    def __init__(self, *, app_icon: Optional[QIcon] = None) -> None:
        super().__init__()
        self.setWindowTitle("DWARF Alpaca Control Center")
        self.resize(1024, 720)
        if app_icon and not app_icon.isNull():
            self.setWindowIcon(app_icon)

        self._settings_path: Optional[Path] = None
        self._settings: Optional[Settings] = None
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
        logging.getLogger().setLevel(logging.INFO)

        self.settings_widget = SettingsOverridesWidget()
        self.provisioning_widget = ProvisioningWidget()
        self.server_widget = ServerControlWidget()
        self._connectivity_summary: str = ""
        self._saved_credentials: OrderedDict[str, str] = OrderedDict()
        self._latest_state: Optional[ConnectivityState] = None
        self._pending_start: Optional[tuple[Settings, bool]] = None

        self.provisioning_widget.provision_requested.connect(self._handle_provision)
        self.provisioning_widget.discovery_requested.connect(self._handle_discover)
        self.provisioning_widget.wifi_scan_requested.connect(self._handle_wifi_scan)
        self.server_widget.start_requested.connect(self._handle_start_server)
        self.server_widget.stop_requested.connect(self._handle_stop_server)

        content = QWidget()
        content_layout = QVBoxLayout(content)

        splitter = QSplitter(Qt.Vertical)
        upper = QWidget()
        upper_layout = QHBoxLayout(upper)
        tabs = QTabWidget()
        tabs.addTab(self.server_widget, "Server")
        tabs.addTab(self.provisioning_widget, "Provisioning")
        tabs.addTab(self.settings_widget, "Settings")
        upper_layout.addWidget(tabs, 2)
        self.help_panel = QLabel()
        self.help_panel.setWordWrap(True)
        self.help_panel.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.help_panel.setMargin(12)
        self.help_panel.setFrameStyle(QFrame.Panel | QFrame.Sunken)
        self.help_panel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        upper_layout.addWidget(self.help_panel, 1)
        splitter.addWidget(upper)
        splitter.addWidget(self.log_console)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        content_layout.addWidget(splitter)
        self.setCentralWidget(content)

        self._create_menu()
        self._tabs = tabs
        self._load_settings(None)
        self._help_messages = {
            0: (
                "Server",
                "<b>Server tab</b><br/>Start or stop the Alpaca service, manage preflight checks,"
                " and monitor server status messages."
            ),
            1: (
                "Provisioning",
                "<b>Provisioning tab</b><br/>Discover DWARF units over BLE, fetch Wi-Fi networks,"
                " and provision STA credentials. Select a device, pick a network,"
                " and provide SSID/password plus optional BLE password overrides."
            ),
            2: (
                "Settings",
                "<b>Settings tab</b><br/>Override server host/port, DWARF IP, and websocket client ID."
                " Choose the correct DWARF generation from the WebSocket Client ID dropdown"
                " (DWARF 3 or DWARF 2) and adjust simulation/preflight controls before launch."
            ),
        }
        self._refresh_state()
        _configure_start_logging(self._settings)
        self._tabs.currentChanged.connect(self._update_help)
        self._update_help(self._tabs.currentIndex())

    # region menu and lifecycle
    def _create_menu(self) -> None:
        menu = self.menuBar().addMenu("File")
        load_action = QAction("Load settings profile…", self)
        load_action.triggered.connect(self._choose_settings_file)
        menu.addAction(load_action)

        reload_action = QAction("Reload", self)
        reload_action.triggered.connect(lambda: self._load_settings(self._settings_path))
        menu.addAction(reload_action)

    def _choose_settings_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select settings YAML",
            str(self._settings_path.parent if self._settings_path else Path.cwd()),
            "YAML files (*.yaml *.yml)",
        )
        if path:
            self._load_settings(Path(path))

    def _load_settings(self, path: Optional[Path]) -> None:
        try:
            settings = load_settings(str(path) if path else None)
        except Exception as exc:
            QMessageBox.critical(self, "Settings", f"Failed to load settings: {exc}")
            return
        self._settings_path = path
        self._settings = settings
        self.settings_widget.populate(settings)
        self.provisioning_widget.set_ble_password(settings.ble_password or "DWARF_12345678")
        self.statusBar().showMessage(
            f"Loaded settings from {path}" if path else "Loaded default environment settings",
            5000,
        )

    def _current_settings(self) -> Settings:
        if not self._settings:
            self._settings = load_settings(str(self._settings_path) if self._settings_path else None)
        return self._settings

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self.log_handler.emitter.message.disconnect(self.log_console.append_message)
        logging.getLogger().removeHandler(self.log_handler)
        if self.server_service.is_running():
            self.server_service.stop()
        super().closeEvent(event)

    # endregion

    # region state display
    def _refresh_state(self) -> None:
        settings = self._current_settings()
        store = create_state_store(settings.state_directory)
        state = store.load()
        self._latest_state = state
        summary = self._format_state_summary(state)
        self._connectivity_summary = summary
        self._saved_credentials = OrderedDict(state.wifi_credentials.items())
        ssid, password = self._get_last_saved_credentials()
        self.provisioning_widget.populate_saved_credentials(ssid, password)
        self._update_help(self._tabs.currentIndex())

    @staticmethod
    def _format_state_summary(state: ConnectivityState) -> str:
        parts = ["<b>Connectivity state</b>"]
        parts.append(f"Mode: {state.mode}")
        parts.append(f"STA IP: {state.sta_ip or 'unknown'}")
        if state.last_error:
            parts.append(f"Last error: {state.last_error}")
        if state.wifi_credentials:
            networks = ", ".join(state.wifi_credentials.keys())
            parts.append(f"Saved networks: {networks}")
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
            status = "running" if self.server_service.is_running() else "stopped"
            sections.append(f"<b>Server status</b><br/>Current state: {status}.")
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
            worker = AsyncWorker(lambda: _preflight_session(settings, timeout=timeout, interval=interval))
            worker.finished_success.connect(lambda _: self._launch_server(settings))
            worker.finished_error.connect(self._on_preflight_error)
            self.server_widget.set_busy("Preflight in progress…")
            self._start_worker(worker)
        else:
            self._launch_server(settings)

    def _on_prestart_provision_success(self, _: object) -> None:
        self.provisioning_widget.show_status("Provisioning succeeded")
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
        worker.finished_error.connect(lambda exc: self._handle_worker_error(exc, "Discovery failed"))
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
        message = "No Wi-Fi networks reported" if not networks else f"Retrieved {len(networks)} network(s)"
        self.provisioning_widget.show_status(message)

    def _on_wifi_error(self, exc: Exception) -> None:
        self.provisioning_widget.show_status(f"Wi-Fi scan failed: {exc}")
        self._handle_worker_error(exc, "Wi-Fi scan failed")

    def _handle_provision(self, payload: dict) -> None:
        worker = AsyncWorker(lambda: self._provision(payload))
        worker.finished_success.connect(lambda _: self._on_provision_success())
        worker.finished_error.connect(lambda exc: self._handle_worker_error(exc, "Provisioning failed"))
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
        self._refresh_state()

    # endregion

    # region server control
    def _handle_start_server(self) -> None:
        if self.server_service.is_running():
            QMessageBox.information(self, "Server", "Server is already running")
            return
        device_address = self.provisioning_widget.device_address_edit.text().strip()
        if not device_address:
            self.provisioning_widget.show_status("Device address is required before starting the server")
            QMessageBox.warning(self, "Server", "Please select or enter a device address before starting.")
            self.provisioning_widget.device_address_edit.setFocus()
            return
        settings = self._build_settings_for_server()
        skip_preflight = self.settings_widget.skip_preflight_checkbox.isChecked()
        self._pending_start = (settings, skip_preflight)
        provisioning_payload = self._build_provisioning_payload()
        if provisioning_payload:
            self.server_widget.set_busy("Provisioning before start…")
            worker = AsyncWorker(lambda: self._provision(provisioning_payload))
            worker.finished_success.connect(self._on_prestart_provision_success)
            worker.finished_error.connect(self._on_prestart_provision_error)
            self._start_worker(worker)
        else:
            self.provisioning_widget.show_status("Skipping provisioning (no credentials provided)")
            self._continue_start_after_provision()

    def _build_settings_for_server(self) -> Settings:
        base = self._current_settings()
        override = self.settings_widget.apply(base)
        state = self._latest_state
        if state is None:
            store = create_state_store(override.state_directory)
            state = store.load()
            self._latest_state = state

        if state:
            detected_mode = (state.mode or "").lower()
            if detected_mode in ("", "unknown"):
                detected_mode = "sta" if state.sta_ip else "ap"
            override.network_mode = detected_mode
            if state.sta_ip:
                override.dwarf_ap_ip = state.sta_ip
                self.settings_widget.dwarf_ip_edit.setText(state.sta_ip)
        if override != base:
            self._settings = override
        return override

    def _launch_server(self, settings: Settings) -> None:
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
        self.server_widget.set_running(status.running, status.message)
        if not status.running:
            self._refresh_state()

    def _handle_server_error(self, message: str) -> None:
        self._handle_worker_error(RuntimeError(message), "Server error")

    # endregion


def main() -> None:
    import sys

    app = QApplication(sys.argv)
    icon = _load_app_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)
    window = MainWindow(app_icon=icon if not icon.isNull() else None)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
