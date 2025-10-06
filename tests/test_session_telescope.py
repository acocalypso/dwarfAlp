import types

import pytest

from dwarf_alpaca.config.settings import Settings
from dwarf_alpaca.dwarf import session as session_module
from dwarf_alpaca.dwarf.session import DwarfSession
from dwarf_alpaca.dwarf.ws_client import DwarfCommandError
from dwarf_alpaca.proto import protocol_pb2


@pytest.mark.asyncio
async def test_telescope_slew_retries_after_busy(monkeypatch):
    session = DwarfSession(Settings())
    session.simulation = False

    async def noop(self, *args, **kwargs):
        return None

    session._ensure_ws = types.MethodType(noop, session)

    busy_state = {"value": True}
    actions: list[tuple[int, int]] = []

    async def fake_send_and_check(self, module_id, command_id, request, *, timeout=10.0, expected_responses=None):
        actions.append((module_id, command_id))
        if command_id == protocol_pb2.DwarfCMD.CMD_ASTRO_START_GOTO_DSO:
            if busy_state["value"]:
                busy_state["value"] = False
                raise DwarfCommandError(module_id, command_id, -11501)
        return None

    session._send_and_check = types.MethodType(fake_send_and_check, session)

    sleep_calls: list[float] = []

    async def instant_sleep(duration):
        sleep_calls.append(duration)
        return None

    monkeypatch.setattr(session_module.asyncio, "sleep", instant_sleep)

    result = await session.telescope_slew_to_coordinates(1.0, 2.0)

    assert result == (1.0, 2.0)
    assert sleep_calls == [0.2]

    goto_calls = [cmd for cmd in actions if cmd[1] == protocol_pb2.DwarfCMD.CMD_ASTRO_START_GOTO_DSO]
    assert len(goto_calls) == 2
    assert (protocol_pb2.ModuleId.MODULE_ASTRO, protocol_pb2.DwarfCMD.CMD_ASTRO_STOP_GOTO) in actions

    motor_stop_calls = [cmd for cmd in actions if cmd[1] == protocol_pb2.DwarfCMD.CMD_STEP_MOTOR_STOP]
    assert len(motor_stop_calls) >= 2


@pytest.mark.asyncio
async def test_telescope_slew_raises_after_repeated_busy(monkeypatch):
    session = DwarfSession(Settings())
    session.simulation = False

    async def noop(self, *args, **kwargs):
        return None

    session._ensure_ws = types.MethodType(noop, session)

    actions: list[tuple[int, int]] = []

    async def fake_send_and_check(self, module_id, command_id, request, *, timeout=10.0, expected_responses=None):
        actions.append((module_id, command_id))
        if command_id == protocol_pb2.DwarfCMD.CMD_ASTRO_START_GOTO_DSO:
            raise DwarfCommandError(module_id, command_id, -11501)
        return None

    session._send_and_check = types.MethodType(fake_send_and_check, session)

    async def instant_sleep(duration):
        return None

    monkeypatch.setattr(session_module.asyncio, "sleep", instant_sleep)

    with pytest.raises(DwarfCommandError) as exc:
        await session.telescope_slew_to_coordinates(3.0, -1.0)

    assert exc.value.code == -11501

    goto_calls = [cmd for cmd in actions if cmd[1] == protocol_pb2.DwarfCMD.CMD_ASTRO_START_GOTO_DSO]
    assert len(goto_calls) == 2
    assert (protocol_pb2.ModuleId.MODULE_ASTRO, protocol_pb2.DwarfCMD.CMD_ASTRO_STOP_GOTO) in actions


    @pytest.mark.asyncio
    async def test_move_axis_prefers_documented_motor_id(monkeypatch):
        session = DwarfSession(Settings())
        session.simulation = False

        async def noop(self, *args, **kwargs):
            return None

        session._ensure_ws = types.MethodType(noop, session)

        captured: list[tuple[int, int, int, bool, float]] = []

        async def fake_send_and_check(self, module_id, command_id, request, *, timeout=10.0, expected_responses=None):
            captured.append((module_id, command_id, request.id, request.direction, request.speed))
            return None

        session._send_and_check = types.MethodType(fake_send_and_check, session)

        await session.telescope_move_axis(0, 1.5)

        assert len(captured) == 1
        module_id, command_id, motor_id, direction, speed = captured[0]
        assert module_id == protocol_pb2.ModuleId.MODULE_MOTOR
        assert command_id == protocol_pb2.DwarfCMD.CMD_STEP_MOTOR_RUN
        assert motor_id == 1
        assert direction is True
        assert abs(speed - 1.5) < 1e-6
        assert session._axis_motor_id[0] == 1
        assert session._axis_direction_polarity[0] == 1


    @pytest.mark.asyncio
    async def test_move_axis_falls_back_to_legacy_motor_id(monkeypatch):
        session = DwarfSession(Settings())
        session.simulation = False

        async def noop(self, *args, **kwargs):
            return None

        session._ensure_ws = types.MethodType(noop, session)

        attempts: list[tuple[int, bool]] = []

        async def fake_send_and_check(self, module_id, command_id, request, *, timeout=10.0, expected_responses=None):
            attempts.append((request.id, request.direction))
            if len(attempts) == 1:
                raise DwarfCommandError(module_id, command_id, 1)
            return None

        session._send_and_check = types.MethodType(fake_send_and_check, session)

        await session.telescope_move_axis(0, -0.5)

        assert len(attempts) == 2
        assert attempts[0] == (1, False)
        assert attempts[1] == (0, False)
        assert session._axis_motor_id[0] == 0
        assert session._axis_direction_polarity[0] == 1


    @pytest.mark.asyncio
    async def test_move_axis_inverts_polarity_when_needed(monkeypatch):
        session = DwarfSession(Settings())
        session.simulation = False

        async def noop(self, *args, **kwargs):
            return None

        session._ensure_ws = types.MethodType(noop, session)

        attempts: list[tuple[int, bool]] = []

        async def fake_send_and_check(self, module_id, command_id, request, *, timeout=10.0, expected_responses=None):
            attempts.append((request.id, request.direction))
            if len(attempts) < 3:
                raise DwarfCommandError(module_id, command_id, 1)
            return None

        session._send_and_check = types.MethodType(fake_send_and_check, session)

        await session.telescope_move_axis(1, 0.8)

        assert len(attempts) == 3
        # Third attempt succeeds with inverted polarity, so direction is False for positive rate
        assert attempts[0][0] == 2
        assert attempts[1][0] == 1
        assert attempts[2][1] is False
        assert session._axis_direction_polarity[1] == -1


    @pytest.mark.asyncio
    async def test_stop_axis_ignores_nonfatal_motor_errors(monkeypatch):
        session = DwarfSession(Settings())
        session.simulation = False
        session._axis_motor_id[0] = 1

        async def noop(self, *args, **kwargs):
            return None

        session._ensure_ws = types.MethodType(noop, session)

        call_count = {"value": 0}

        async def fake_send_and_check(self, module_id, command_id, request, *, timeout=10.0, expected_responses=None):
            if command_id == protocol_pb2.DwarfCMD.CMD_STEP_MOTOR_STOP and call_count["value"] == 0:
                call_count["value"] += 1
                raise DwarfCommandError(module_id, command_id, 1)
            return None

        session._send_and_check = types.MethodType(fake_send_and_check, session)

        await session.telescope_stop_axis(0)
        assert call_count["value"] == 1
