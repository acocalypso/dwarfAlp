import sys
from importlib.metadata import version

import pytest

from dwarf_alpaca import __version__
from dwarf_alpaca.cli import main
from dwarf_alpaca.config.settings import Settings
from dwarf_alpaca.devices.camera import get_driver_version as camera_driver_version
from dwarf_alpaca.devices.filterwheel import get_driver_version as filterwheel_driver_version
from dwarf_alpaca.devices.focuser import get_driver_version as focuser_driver_version
from dwarf_alpaca.devices.telescope import get_driver_version as telescope_driver_version
from dwarf_alpaca.discovery import build_discovery_payload
from dwarf_alpaca.server import build_app


def test_distribution_version_is_project_version():
    assert __version__ == version("dwarf-alpaca") == "0.1.1"


def test_server_metadata_uses_project_version():
    app = build_app(Settings(force_simulation=True, discovery_enabled=False))
    discovery = build_discovery_payload(Settings(), "192.168.1.100")

    assert app.version == __version__
    assert discovery["ManufacturerVersion"] == __version__


@pytest.mark.parametrize(
    "driver_version",
    [
        camera_driver_version,
        filterwheel_driver_version,
        focuser_driver_version,
        telescope_driver_version,
    ],
)
def test_alpaca_devices_report_project_version(driver_version):
    assert driver_version()["Value"] == __version__


def test_cli_reports_project_version(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["dwarf-alpaca", "--version"])

    with pytest.raises(SystemExit) as exit_info:
        main()

    assert exit_info.value.code == 0
    assert capsys.readouterr().out.strip() == f"dwarf-alpaca {__version__}"
