import time
from unittest.mock import AsyncMock

import pytest

from dwarf_alpaca.config.settings import Settings
from dwarf_alpaca.dwarf.session import DwarfSession
from dwarf_alpaca.proto import protocol_pb2


@pytest.mark.asyncio
async def test_focuser_move_positive_delta_uses_far_focus_direction():
    settings = Settings(force_simulation=False)
    session = DwarfSession(settings)
    session.focuser_state.position = 100
    session._ensure_ws = AsyncMock()

    captured = []

    async def fake_send_and_check(module_id, command_id, request):
        captured.append(request.direction)
        session.focuser_state.position += 1
        session._focus_update_event.set()

    session._send_and_check = fake_send_and_check  # type: ignore[assignment]

    await session.focuser_move(5)

    assert captured, "no focuser commands were dispatched"
    assert all(direction == 0 for direction in captured)


@pytest.mark.asyncio
async def test_focuser_move_negative_delta_uses_near_focus_direction():
    settings = Settings(force_simulation=False)
    session = DwarfSession(settings)
    session.focuser_state.position = 200
    session._ensure_ws = AsyncMock()

    captured = []

    async def fake_send_and_check(module_id, command_id, request):
        captured.append(request.direction)
        session.focuser_state.position -= 1
        session._focus_update_event.set()

    session._send_and_check = fake_send_and_check  # type: ignore[assignment]

    await session.focuser_move(-4)

    assert captured, "no focuser commands were dispatched"
    assert all(direction == 1 for direction in captured)


@pytest.mark.asyncio
async def test_continuous_move_triggers_trim_on_overshoot():
    settings = Settings(force_simulation=False)
    session = DwarfSession(settings)
    session.focuser_state.position = 0
    session._ensure_ws = AsyncMock()

    async def fake_send_and_check(module_id, command_id, request):
        if command_id == protocol_pb2.DwarfCMD.CMD_FOCUS_START_MANUAL_CONTINU_FOCUS:
            session.focuser_state.position = 620
            session.focuser_state.last_update = time.time()
            session._focus_update_event.set()
        elif command_id == protocol_pb2.DwarfCMD.CMD_FOCUS_STOP_MANUAL_CONTINU_FOCUS:
            session._focus_update_event.set()
        else:
            raise AssertionError(f"Unexpected focus command {command_id}")

    session._send_and_check = fake_send_and_check  # type: ignore[assignment]

    trim_mock = AsyncMock()
    session._focus_nudge_to_target = trim_mock  # type: ignore[assignment]

    await session.focuser_move(600)

    trim_mock.assert_awaited_once_with(600, tolerance=settings.focuser_target_tolerance_steps)
