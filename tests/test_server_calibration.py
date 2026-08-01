from __future__ import annotations

import pytest

from dwarf_alpaca.config.settings import Settings
from dwarf_alpaca.server import _calibrate_after_start


class DummySession:
    def __init__(self) -> None:
        self.acquired: list[str] = []
        self.released: list[str] = []
        self.calibration_calls = 0

    async def acquire(self, device: str) -> None:
        self.acquired.append(device)

    async def release(self, device: str) -> None:
        self.released.append(device)

    async def ensure_calibration(self) -> None:
        self.calibration_calls += 1


@pytest.mark.asyncio
@pytest.mark.parametrize("model", ["dwarf3", "dwarfmini"])
async def test_calibration_runs_after_start_for_supported_models(monkeypatch, model: str) -> None:
    session = DummySession()

    async def fake_get_session() -> DummySession:
        return session

    monkeypatch.setattr("dwarf_alpaca.server.get_session", fake_get_session)

    await _calibrate_after_start(
        Settings(dwarf_device_model=model, calibrate_after_server_start=True)
    )

    assert session.acquired == ["telescope"]
    assert session.calibration_calls == 1
    assert session.released == ["telescope"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "settings",
    [
        Settings(dwarf_device_model="dwarf2", calibrate_after_server_start=True),
        Settings(dwarf_device_model="dwarf3", calibrate_after_server_start=False),
        Settings(
            dwarf_device_model="dwarfmini",
            calibrate_after_server_start=True,
            force_simulation=True,
        ),
    ],
)
async def test_calibration_after_start_skips_unsupported_or_disabled_modes(
    monkeypatch, settings: Settings
) -> None:
    async def fail_get_session():
        raise AssertionError("session should not be opened")

    monkeypatch.setattr("dwarf_alpaca.server.get_session", fail_get_session)

    await _calibrate_after_start(settings)
