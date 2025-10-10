import types

import pytest

from dwarf_alpaca.cli import _preflight_session, start_command
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


@pytest.mark.asyncio
async def test_preflight_runs_calibration(monkeypatch):
    class DummySession:
        def __init__(self) -> None:
            self.acquire_calls = 0
            self.release_calls = 0
            self.calibration_calls = 0
            self.wait_calls = 0
            self.has_master_lock = True

        async def acquire(self, device: str) -> None:  # pragma: no cover - simple stub
            self.acquire_calls += 1

        async def release(self, device: str) -> None:  # pragma: no cover - simple stub
            self.release_calls += 1

        async def ensure_calibration(self) -> None:
            self.calibration_calls += 1

        async def _wait_for_calibration_ready(self) -> None:
            self.wait_calls += 1

    dummy_session = DummySession()

    async def fake_get_session():  # pragma: no cover - simple stub
        return dummy_session

    def fake_configure_session(settings):  # pragma: no cover - simple stub
        return None

    monkeypatch.setattr("dwarf_alpaca.cli.get_session", fake_get_session)
    monkeypatch.setattr("dwarf_alpaca.cli.configure_session", fake_configure_session)

    settings = Settings(force_simulation=False)

    await _preflight_session(settings, timeout=0.1, interval=0.01)

    assert dummy_session.acquire_calls == 1
    assert dummy_session.release_calls == 1
    assert dummy_session.calibration_calls == 1
    assert dummy_session.wait_calls == 1
