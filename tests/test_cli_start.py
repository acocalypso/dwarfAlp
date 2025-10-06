import types

import pytest

from dwarf_alpaca.cli import start_command
from dwarf_alpaca.config.settings import Settings


class DummyStateStore:
    def __init__(self, sta_ip: str | None = None, mode: str = "unknown") -> None:
        self._sta_ip = sta_ip
        self._mode = mode

    def load(self) -> types.SimpleNamespace:
        return types.SimpleNamespace(sta_ip=self._sta_ip, mode=self._mode)


@pytest.mark.asyncio
async def test_start_command_uses_guide_when_no_ssid(monkeypatch):
    called = {
        "guide": False,
        "server": False,
    }

    async def fake_provision_guide_command(**kwargs):
        called["guide"] = True

    async def fake_run_server(settings):
        called["server"] = True

    def fake_state_store(_):
        return DummyStateStore(sta_ip="10.0.0.5", mode="sta")

    # make sure direct provisioning isn't invoked accidentally
    async def fail_provision_command(**kwargs):  # pragma: no cover - defensive
        raise AssertionError("provision_command should not be called without an SSID")

    monkeypatch.setattr("dwarf_alpaca.cli.provision_guide_command", fake_provision_guide_command)
    monkeypatch.setattr("dwarf_alpaca.cli.provision_command", fail_provision_command)
    monkeypatch.setattr("dwarf_alpaca.cli.create_state_store", fake_state_store)
    monkeypatch.setattr("dwarf_alpaca.cli.run_server", fake_run_server)

    settings = Settings(force_simulation=True)

    await start_command(
        settings=settings,
        ssid=None,
        password=None,
        adapter=None,
        ble_password=None,
        device_address=None,
        skip_provision=False,
        timeout=1.0,
        interval=0.1,
        ws_client_id=None,
    )

    assert called["guide"] is True
    assert called["server"] is True
    assert settings.dwarf_ap_ip == "10.0.0.5"


@pytest.mark.asyncio
async def test_start_command_skips_guide_when_provision_disabled(monkeypatch):
    called = {
        "guide": False,
        "server": False,
    }

    async def fake_provision_guide_command(**kwargs):  # pragma: no cover - defensive
        called["guide"] = True

    async def fake_run_server(settings):
        called["server"] = True

    def fake_state_store(_):
        return DummyStateStore(sta_ip="10.0.0.8", mode="sta")

    monkeypatch.setattr("dwarf_alpaca.cli.provision_guide_command", fake_provision_guide_command)
    monkeypatch.setattr("dwarf_alpaca.cli.create_state_store", fake_state_store)
    monkeypatch.setattr("dwarf_alpaca.cli.run_server", fake_run_server)

    settings = Settings(force_simulation=True)

    await start_command(
        settings=settings,
        ssid=None,
        password=None,
        adapter=None,
        ble_password=None,
        device_address=None,
        skip_provision=True,
        timeout=1.0,
        interval=0.1,
        ws_client_id=None,
    )

    assert called["guide"] is False
    assert called["server"] is True
    assert settings.dwarf_ap_ip == "10.0.0.8"
