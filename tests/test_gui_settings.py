import pytest
import structlog
from PySide6.QtWidgets import QApplication

from dwarf_alpaca.dwarf.state import ConnectivityState
from dwarf_alpaca.gui.app import MainWindow, _configure_gui_structlog


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def test_gui_structlog_works_without_console_streams(monkeypatch):
    monkeypatch.setattr("sys.stdout", None)
    monkeypatch.setattr("sys.stderr", None)

    _configure_gui_structlog()

    structlog.get_logger("test.gui").debug("background_task_cancelled")


def test_build_settings_respects_manually_entered_ip(qapp, tmp_path):
    window = MainWindow()
    try:
        # ensure settings writes go to a temporary directory
        window._settings = window._settings.model_copy(update={"state_directory": tmp_path})  # type: ignore[attr-defined]
        window._latest_state = ConnectivityState(sta_ip="10.0.0.5", mode="sta")  # type: ignore[attr-defined]
        window.settings_widget.dwarf_ip_edit.setText("10.0.0.42")

        settings = window._build_settings_for_server()

        assert settings.dwarf_ap_ip == "10.0.0.42"
        assert settings.network_mode == "sta"
        assert window.settings_widget.dwarf_ip_edit.text() == "10.0.0.42"
    finally:
        window.close()


def test_start_allows_direct_ip_without_device_address(qapp):
    window = MainWindow()
    try:
        started_with = None

        def fake_start(settings):
            nonlocal started_with
            started_with = settings

        window.server_service.start = fake_start  # type: ignore[assignment]
        window.provisioning_widget.device_address_edit.clear()
        window.settings_widget.dwarf_ip_edit.setText("192.168.178.97")
        window.settings_widget.skip_preflight_checkbox.setChecked(True)

        window._handle_start_server()

        assert started_with is not None
        assert started_with.dwarf_ap_ip == "192.168.178.97"
        assert window._pending_start is None
    finally:
        window.close()


def test_start_does_not_automatically_provision_saved_wifi(qapp):
    window = MainWindow()
    try:
        provision_called = False
        started_with = None

        async def fake_provision(payload):
            nonlocal provision_called
            provision_called = True

        def fake_start(settings):
            nonlocal started_with
            started_with = settings

        window._provision = fake_provision  # type: ignore[assignment]
        window.server_service.start = fake_start  # type: ignore[assignment]
        window.provisioning_widget.ssid_edit.setText("saved-network")
        window.provisioning_widget.password_edit.setText("saved-password")
        window.settings_widget.skip_preflight_checkbox.setChecked(True)

        window._handle_start_server()

        assert started_with is not None
        assert not provision_called
    finally:
        window.close()


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (
            {"device_address": "", "ssid": "network", "password": "secret"},
            "Select a discovered DWARF device",
        ),
        (
            {"device_address": "AA:BB", "ssid": "", "password": "secret"},
            "Select or enter a Wi-Fi network",
        ),
        (
            {"device_address": "AA:BB", "ssid": "network", "password": ""},
            "Enter the Wi-Fi password",
        ),
    ],
)
def test_provision_reports_missing_inputs(qapp, payload, expected):
    window = MainWindow()
    try:
        window._handle_provision(payload)
        assert expected in window.provisioning_widget.status_label.text()
        assert not window._workers
    finally:
        window.close()


def test_settings_widget_can_select_dwarf_mini(qapp):
    window = MainWindow()
    try:
        model_combo = window.settings_widget.device_model_combo
        idx = model_combo.findData("dwarfmini")
        assert idx >= 0

        model_combo.setCurrentIndex(idx)
        settings = window._build_settings_for_server()

        assert settings.dwarf_device_model == "dwarfmini"
    finally:
        window.close()
