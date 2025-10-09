import pytest

from PySide6.QtWidgets import QApplication, QMessageBox

from dwarf_alpaca.gui.app import MainWindow
from dwarf_alpaca.dwarf.state import ConnectivityState


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def test_build_settings_uses_latest_sta_ip(qapp, tmp_path):
    window = MainWindow()
    try:
        # ensure settings writes go to a temporary directory
        window._settings = window._settings.model_copy(update={"state_directory": tmp_path})  # type: ignore[attr-defined]
        window._latest_state = ConnectivityState(sta_ip="10.0.0.5", mode="sta")  # type: ignore[attr-defined]

        settings = window._build_settings_for_server()

        assert settings.dwarf_ap_ip == "10.0.0.5"
        assert settings.network_mode == "sta"
        assert window.settings_widget.dwarf_ip_edit.text() == "10.0.0.5"
    finally:
        window.close()


def test_start_blocked_when_device_address_missing(qapp, monkeypatch):
    window = MainWindow()
    try:
        warnings: list[tuple[tuple, dict]] = []

        def fake_warning(*args, **kwargs):
            warnings.append((args, kwargs))
            return QMessageBox.StandardButton.Ok

        monkeypatch.setattr(QMessageBox, "warning", fake_warning)

        start_called = False

        def fake_start(settings):
            nonlocal start_called
            start_called = True

        window.server_service.start = fake_start  # type: ignore[assignment]
        window.provisioning_widget.device_address_edit.clear()

        window._handle_start_server()

        assert not start_called
        assert window._pending_start is None
        assert window.provisioning_widget.status_label.text() == "Device address is required before starting the server"
        assert warnings, "Expected warning dialog when device address is missing"
    finally:
        window.close()
