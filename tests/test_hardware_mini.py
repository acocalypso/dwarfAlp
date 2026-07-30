from __future__ import annotations

import os

import pytest

from dwarf_alpaca.config.settings import Settings
from dwarf_alpaca.dwarf.session import DwarfSession

pytestmark = pytest.mark.hardware


def _hardware_enabled() -> bool:
    return os.getenv("DWARF_ALPACA_RUN_HARDWARE", "").strip() == "1"


@pytest.mark.asyncio
async def test_mini_safe_handshake_master_lock_and_camera_open():
    if not _hardware_enabled():
        pytest.skip("set DWARF_ALPACA_RUN_HARDWARE=1 for physical-device tests")
    model = os.getenv("DWARF_ALPACA_DWARF_DEVICE_MODEL", "dwarfmini")
    if model.strip().lower().replace(" ", "") != "dwarfmini":
        pytest.skip("this hardware test is restricted to DWARF mini")

    settings = Settings(
        dwarf_device_model="dwarfmini",
        force_simulation=False,
        dwarf_ap_ip=os.getenv("DWARF_ALPACA_DWARF_AP_IP", "192.168.88.1"),
    )
    session = DwarfSession(settings)
    try:
        await session.acquire("camera")
        await session.camera_connect()
        assert session._ws_client.connected
        assert session.has_master_lock
        assert session.camera_state.connected
        assert session._ws_client.minor_version == 20
        assert session._ws_client.device_id == 4
        session.camera_state.duration = 1.0
        session.camera_state.requested_gain = 60
        await session._ensure_exposure_settings(1.0)
        await session._ensure_gain_settings()
        await session._configure_astro_capture(frames=1, binning=(1, 1))
        assert session.camera_state.applied_duration == 1.0
        assert session.camera_state.applied_gain_value == 60
        assert session.camera_state.applied_frame_count == 1
        assert session.camera_state.applied_bin == (1, 1)
    finally:
        if session.camera_state.connected:
            await session.camera_disconnect()
        await session.release("camera")
        await session.shutdown()
