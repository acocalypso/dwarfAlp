import math
import time
import types
from typing import Any, Dict

import pytest

from dwarf_alpaca.config.settings import Settings
from dwarf_alpaca.dwarf import session as session_module
from dwarf_alpaca.dwarf.session import DwarfSession
from dwarf_alpaca.dwarf.ws_client import DwarfCommandError
from dwarf_alpaca.proto import protocol_pb2
from dwarf_alpaca.proto.dwarf_messages import TYPE_NOTIFICATION, WsPacket
from dwarf_alpaca.proto.notify_pb2 import AstroCalibrationState, CalibrationResult


@pytest.mark.asyncio
async def test_explicit_mini_calibration_uses_shared_v3_command() -> None:
    session = DwarfSession(Settings(dwarf_device_model="dwarfmini"))
    session.simulation = False
    calls: list[tuple[int, int]] = []
    captured_expected_responses = None

    async def fake_send_and_check(
        self, module_id, command_id, request, *, timeout=10.0, expected_responses=None
    ):
        nonlocal captured_expected_responses
        calls.append((module_id, command_id))
        captured_expected_responses = expected_responses

    session._send_and_check = types.MethodType(fake_send_and_check, session)

    await session.ensure_calibration()

    assert calls == [
        (
            protocol_pb2.ModuleId.MODULE_ASTRO,
            protocol_pb2.DwarfCMD.CMD_ASTRO_START_CALIBRATION,
        )
    ]
    assert captured_expected_responses == {
        (
            protocol_pb2.ModuleId.MODULE_NOTIFY,
            protocol_pb2.DwarfCMD.CMD_NOTIFY_CALIBRATION_RESULT,
        ): CalibrationResult,
    }
    assert session.get_calibration_status()["status"] == "successful"


@pytest.mark.asyncio
async def test_calibration_notifications_record_progress_and_success() -> None:
    session = DwarfSession(Settings(dwarf_device_model="dwarfmini"))
    session.simulation = False

    state = AstroCalibrationState(state=4, plate_solving_times=2)
    state_packet = WsPacket(
        module_id=protocol_pb2.ModuleId.MODULE_NOTIFY,
        cmd=protocol_pb2.DwarfCMD.CMD_NOTIFY_STATE_ASTRO_CALIBRATION,
        type=TYPE_NOTIFICATION,
        data=state.SerializeToString(),
    )
    await session._handle_notification(state_packet)

    progress = session.get_calibration_status()
    assert progress["status"] == "plate solving"
    assert progress["detail"] == "Plate solving attempt 2"

    result = CalibrationResult(azi=183.25, alt=47.5)
    result_packet = WsPacket(
        module_id=protocol_pb2.ModuleId.MODULE_NOTIFY,
        cmd=protocol_pb2.DwarfCMD.CMD_NOTIFY_CALIBRATION_RESULT,
        type=TYPE_NOTIFICATION,
        data=result.SerializeToString(),
    )
    await session._handle_notification(result_packet)

    completed = session.get_calibration_status()
    assert completed["status"] == "successful"
    assert completed["azimuth"] == pytest.approx(183.25)
    assert completed["altitude"] == pytest.approx(47.5)
    assert "183.25" in completed["detail"]


@pytest.mark.asyncio
async def test_calibration_timeout_is_not_reported_as_successful() -> None:
    session = DwarfSession(Settings(dwarf_device_model="dwarfmini"))
    session.simulation = False

    async def timeout(self, *args, **kwargs):
        raise TimeoutError

    session._send_and_check = types.MethodType(timeout, session)

    with pytest.raises(TimeoutError):
        await session.ensure_calibration()

    outcome = session.get_calibration_status()
    assert outcome["status"] == "not confirmed"
    assert "timeout" in outcome["detail"].lower()


def test_auto_calibration_is_enabled_for_requested_slews_by_default() -> None:
    settings = Settings()

    assert settings.auto_calibrate_on_slew is True
    assert settings.calibration_wait_for_slew_seconds >= settings.calibration_timeout_seconds


@pytest.mark.asyncio
async def test_telescope_slew_recalibrates_and_retries_after_goto_failure(monkeypatch):
    session = DwarfSession(Settings(dwarf_device_model="dwarf3"))
    session.simulation = False

    async def noop(self, *args, **kwargs):
        return None

    session._ensure_ws = types.MethodType(noop, session)
    actions: list[int] = []
    goto_attempts = 0

    async def fake_send_and_check(
        self, module_id, command_id, request, *, timeout=10.0, expected_responses=None
    ):
        nonlocal goto_attempts
        actions.append(command_id)
        if command_id == protocol_pb2.DwarfCMD.CMD_ASTRO_START_GOTO_DSO:
            goto_attempts += 1
            if goto_attempts == 1:
                raise DwarfCommandError(module_id, command_id, protocol_pb2.CODE_ASTRO_GOTO_FAILED)

    session._send_and_check = types.MethodType(fake_send_and_check, session)

    async def instant_sleep(_duration):
        return None

    monkeypatch.setattr(session_module.asyncio, "sleep", instant_sleep)

    result = await session.telescope_slew_to_coordinates(14.6817, 69.5667)

    assert result == (14.6817, 69.5667)
    assert actions.count(protocol_pb2.DwarfCMD.CMD_ASTRO_START_CALIBRATION) == 2
    assert actions.count(protocol_pb2.DwarfCMD.CMD_ASTRO_START_GOTO_DSO) == 2
    assert protocol_pb2.DwarfCMD.CMD_ASTRO_STOP_GOTO in actions


@pytest.mark.asyncio
async def test_telescope_slew_retries_after_busy(monkeypatch):
    settings = Settings()
    settings.auto_calibrate_on_slew = True
    session = DwarfSession(settings)
    session.simulation = False

    async def noop(self, *args, **kwargs):
        return None

    session._ensure_ws = types.MethodType(noop, session)

    stop_calls: list[tuple[int, bool]] = []
    original_stop_axis = session.telescope_stop_axis

    async def recording_stop_axis(self, axis: int, *, ensure_ws: bool = True):
        stop_calls.append((axis, ensure_ws))
        return await original_stop_axis(axis, ensure_ws=ensure_ws)

    session.telescope_stop_axis = types.MethodType(recording_stop_axis, session)

    busy_state = {"value": True}
    actions: list[tuple[int, int]] = []

    async def fake_send_and_check(
        self, module_id, command_id, request, *, timeout=10.0, expected_responses=None
    ):
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

    goto_calls = [
        cmd for cmd in actions if cmd[1] == protocol_pb2.DwarfCMD.CMD_ASTRO_START_GOTO_DSO
    ]
    assert len(goto_calls) == 2
    assert (
        protocol_pb2.ModuleId.MODULE_ASTRO,
        protocol_pb2.DwarfCMD.CMD_ASTRO_STOP_GOTO,
    ) in actions

    calibration_calls = [
        cmd for cmd in actions if cmd[1] == protocol_pb2.DwarfCMD.CMD_ASTRO_START_CALIBRATION
    ]
    assert calibration_calls == [
        (protocol_pb2.ModuleId.MODULE_ASTRO, protocol_pb2.DwarfCMD.CMD_ASTRO_START_CALIBRATION)
    ]

    assert len(stop_calls) >= 4
    assert {axis for axis, _ in stop_calls} == {0, 1}


@pytest.mark.asyncio
async def test_telescope_slew_raises_after_repeated_busy(monkeypatch):
    settings = Settings()
    settings.auto_calibrate_on_slew = True
    session = DwarfSession(settings)
    session.simulation = False

    async def noop(self, *args, **kwargs):
        return None

    session._ensure_ws = types.MethodType(noop, session)

    actions: list[tuple[int, int]] = []

    async def fake_send_and_check(
        self, module_id, command_id, request, *, timeout=10.0, expected_responses=None
    ):
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

    goto_calls = [
        cmd for cmd in actions if cmd[1] == protocol_pb2.DwarfCMD.CMD_ASTRO_START_GOTO_DSO
    ]
    assert len(goto_calls) == 2
    assert (
        protocol_pb2.ModuleId.MODULE_ASTRO,
        protocol_pb2.DwarfCMD.CMD_ASTRO_STOP_GOTO,
    ) in actions

    calibration_calls = [
        cmd for cmd in actions if cmd[1] == protocol_pb2.DwarfCMD.CMD_ASTRO_START_CALIBRATION
    ]
    assert calibration_calls == [
        (protocol_pb2.ModuleId.MODULE_ASTRO, protocol_pb2.DwarfCMD.CMD_ASTRO_START_CALIBRATION)
    ]


@pytest.mark.asyncio
async def test_telescope_slew_refreshes_calibration_after_expiry(monkeypatch):
    settings = Settings()
    settings.auto_calibrate_on_slew = True
    settings.calibration_valid_seconds = 60.0
    session = DwarfSession(settings)
    session.simulation = False

    async def noop(self, *args, **kwargs):
        return None

    session._ensure_ws = types.MethodType(noop, session)

    actions: list[tuple[int, int]] = []

    async def fake_send_and_check(
        self, module_id, command_id, request, *, timeout=10.0, expected_responses=None
    ):
        actions.append((module_id, command_id))
        return None

    session._send_and_check = types.MethodType(fake_send_and_check, session)

    await session.telescope_slew_to_coordinates(1.2, -3.4)

    assert (
        protocol_pb2.ModuleId.MODULE_ASTRO,
        protocol_pb2.DwarfCMD.CMD_ASTRO_START_CALIBRATION,
    ) in actions
    assert (
        protocol_pb2.ModuleId.MODULE_ASTRO,
        protocol_pb2.DwarfCMD.CMD_ASTRO_START_GOTO_DSO,
    ) in actions

    actions.clear()

    await session.telescope_slew_to_coordinates(2.5, 1.0)

    assert (
        protocol_pb2.ModuleId.MODULE_ASTRO,
        protocol_pb2.DwarfCMD.CMD_ASTRO_START_CALIBRATION,
    ) not in actions
    assert (
        protocol_pb2.ModuleId.MODULE_ASTRO,
        protocol_pb2.DwarfCMD.CMD_ASTRO_START_GOTO_DSO,
    ) in actions

    session._last_calibration_time = time.time() - (settings.calibration_valid_seconds + 5.0)
    session._last_calibration_ip = settings.dwarf_ap_ip
    actions.clear()

    await session.telescope_slew_to_coordinates(-4.0, 0.5)

    calibration_calls = [
        cmd for cmd in actions if cmd[1] == protocol_pb2.DwarfCMD.CMD_ASTRO_START_CALIBRATION
    ]
    assert calibration_calls == [
        (protocol_pb2.ModuleId.MODULE_ASTRO, protocol_pb2.DwarfCMD.CMD_ASTRO_START_CALIBRATION)
    ]
    assert (
        protocol_pb2.ModuleId.MODULE_ASTRO,
        protocol_pb2.DwarfCMD.CMD_ASTRO_START_GOTO_DSO,
    ) in actions


@pytest.mark.asyncio
async def test_telescope_slew_uses_configured_timeout(monkeypatch):
    settings = Settings()
    settings.goto_command_timeout_seconds = 42.5
    session = DwarfSession(settings)
    session.simulation = False

    async def noop(self, *args, **kwargs):
        return None

    session._ensure_ws = types.MethodType(noop, session)

    captured_timeout = {}

    async def fake_send_and_check(
        self, module_id, command_id, request, *, timeout=10.0, expected_responses=None
    ):
        captured_timeout["value"] = timeout
        return None

    session._send_and_check = types.MethodType(fake_send_and_check, session)

    await session.telescope_slew_to_coordinates(1.2, 3.4)

    assert "value" in captured_timeout
    assert captured_timeout["value"] == pytest.approx(settings.goto_command_timeout_seconds)


@pytest.mark.asyncio
async def test_acquire_telescope_does_not_schedule_calibration(monkeypatch):
    session = DwarfSession(Settings())
    session.simulation = False

    async def fake_ensure_ws(self, *args, **kwargs):
        self._master_lock_acquired = True

    session._ensure_ws = types.MethodType(fake_ensure_ws, session)

    scheduled_tasks: list[Any] = []

    def fake_create_task(coro):
        scheduled_tasks.append(coro)
        raise AssertionError("Calibration task should not be scheduled during acquire")

    monkeypatch.setattr(session_module.asyncio, "create_task", fake_create_task)

    await session.acquire("telescope")

    assert scheduled_tasks == []


@pytest.mark.asyncio
async def test_acquire_telescope_does_not_schedule_even_without_recent_cal(monkeypatch):
    session = DwarfSession(Settings())
    session.simulation = False
    session._last_calibration_time = None
    session._last_calibration_ip = None

    async def fake_ensure_ws(self, *args, **kwargs):
        self._master_lock_acquired = True

    session._ensure_ws = types.MethodType(fake_ensure_ws, session)

    scheduled_tasks: list[Any] = []

    def fake_create_task(coro):
        scheduled_tasks.append(coro)
        raise AssertionError("Calibration task should not be scheduled during acquire")

    monkeypatch.setattr(session_module.asyncio, "create_task", fake_create_task)

    await session.acquire("telescope")

    assert scheduled_tasks == []


@pytest.mark.asyncio
async def test_acquire_focuser_does_not_schedule_calibration(monkeypatch):
    session = DwarfSession(Settings())
    session.simulation = False

    async def fake_ensure_ws(self, *args, **kwargs):
        self._master_lock_acquired = True

    session._ensure_ws = types.MethodType(fake_ensure_ws, session)

    scheduled_tasks: list[Any] = []

    def fake_create_task(coro):
        scheduled_tasks.append(coro)
        raise AssertionError("Calibration task should not be scheduled for focuser acquire")

    monkeypatch.setattr(session_module.asyncio, "create_task", fake_create_task)

    await session.acquire("focuser")

    assert scheduled_tasks == []


@pytest.mark.asyncio
async def test_release_keeps_recent_calibration(monkeypatch):
    settings = Settings()
    session = DwarfSession(settings)
    session.simulation = False

    # Prepare calibration state
    now = time.time()
    session._last_calibration_time = now
    session._last_calibration_ip = settings.dwarf_ap_ip

    # Ensure release path thinks all refs are active then going to zero
    for key in session._refs:
        session._refs[key] = 0
    session._refs["telescope"] = 1

    async def fake_ws_close(_self=None):
        return None

    async def fake_http_close(_self=None):
        return None

    monkeypatch.setattr(type(session._ws_client), "close", fake_ws_close)
    monkeypatch.setattr(type(session._http_client), "aclose", fake_http_close)

    await session.release("telescope")

    assert session._last_calibration_time == now
    assert session._last_calibration_ip == settings.dwarf_ap_ip


@pytest.mark.asyncio
async def test_telescope_move_axis_sends_joystick_command(monkeypatch):
    session = DwarfSession(Settings())
    session.simulation = False

    async def noop(self, *args, **kwargs):
        return None

    session._ensure_ws = types.MethodType(noop, session)

    captured: list[Dict[str, Any]] = []

    async def fake_send_and_check(
        self, module_id, command_id, request, *, timeout=10.0, expected_responses=None
    ):
        captured.append(
            {
                "module_id": module_id,
                "command_id": command_id,
                "vector_angle": getattr(request, "vector_angle", None),
                "vector_length": getattr(request, "vector_length", None),
                "speed": getattr(request, "speed", None),
            }
        )
        return None

    session._send_and_check = types.MethodType(fake_send_and_check, session)

    await session.telescope_move_axis(0, 1.5)

    assert len(captured) == 1
    entry = captured[0]
    assert entry["module_id"] == protocol_pb2.ModuleId.MODULE_MOTOR
    assert entry["command_id"] == protocol_pb2.DwarfCMD.CMD_STEP_MOTOR_SERVICE_JOYSTICK
    assert entry["vector_angle"] == pytest.approx(0.0)
    assert entry["vector_length"] == pytest.approx(1.0)
    assert entry["speed"] == pytest.approx(1.5)
    assert session._manual_axis_rates[0] == pytest.approx(1.5)
    assert session._joystick_active is True


@pytest.mark.asyncio
async def test_telescope_move_axis_clamps_speed(monkeypatch):
    session = DwarfSession(Settings())
    session.simulation = False

    async def noop(self, *args, **kwargs):
        return None

    session._ensure_ws = types.MethodType(noop, session)

    captured: list[Dict[str, Any]] = []

    async def fake_send_and_check(
        self, module_id, command_id, request, *, timeout=10.0, expected_responses=None
    ):
        captured.append(
            {
                "module_id": module_id,
                "command_id": command_id,
                "vector_angle": getattr(request, "vector_angle", None),
                "vector_length": getattr(request, "vector_length", None),
                "speed": getattr(request, "speed", None),
            }
        )
        return None

    session._send_and_check = types.MethodType(fake_send_and_check, session)

    await session.telescope_move_axis(0, 100.0)

    assert captured
    entry = captured[-1]
    assert entry["speed"] == pytest.approx(30.0)
    assert entry["vector_length"] == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_telescope_move_axis_combines_axes(monkeypatch):
    session = DwarfSession(Settings())
    session.simulation = False

    async def noop(self, *args, **kwargs):
        return None

    session._ensure_ws = types.MethodType(noop, session)

    captured: list[Dict[str, Any]] = []

    async def fake_send_and_check(
        self, module_id, command_id, request, *, timeout=10.0, expected_responses=None
    ):
        captured.append(
            {
                "module_id": module_id,
                "command_id": command_id,
                "vector_angle": getattr(request, "vector_angle", None),
                "vector_length": getattr(request, "vector_length", None),
                "speed": getattr(request, "speed", None),
            }
        )
        return None

    session._send_and_check = types.MethodType(fake_send_and_check, session)

    await session.telescope_move_axis(0, 5.0)
    await session.telescope_move_axis(1, 5.0)

    assert len(captured) == 2
    angle = captured[-1]["vector_angle"]
    assert angle == pytest.approx(45.0)
    assert captured[-1]["vector_length"] == pytest.approx(1.0)
    assert captured[-1]["speed"] == pytest.approx(math.hypot(5.0, 5.0))


@pytest.mark.asyncio
async def test_telescope_stop_axis_sends_stop_when_idle(monkeypatch):
    session = DwarfSession(Settings())
    session.simulation = False

    async def noop(self, *args, **kwargs):
        return None

    session._ensure_ws = types.MethodType(noop, session)

    captured: list[Dict[str, Any]] = []

    async def fake_send_and_check(
        self, module_id, command_id, request, *, timeout=10.0, expected_responses=None
    ):
        captured.append(
            {
                "module_id": module_id,
                "command_id": command_id,
                "vector_angle": getattr(request, "vector_angle", None),
                "vector_length": getattr(request, "vector_length", None),
                "speed": getattr(request, "speed", None),
            }
        )
        return None

    session._send_and_check = types.MethodType(fake_send_and_check, session)

    await session.telescope_move_axis(0, 2.0)
    assert session._joystick_active is True

    await session.telescope_stop_axis(0)

    assert len(captured) == 2
    assert captured[-1]["command_id"] == protocol_pb2.DwarfCMD.CMD_STEP_MOTOR_SERVICE_JOYSTICK_STOP
    assert session._joystick_active is False


@pytest.mark.asyncio
async def test_telescope_stop_axis_noop_when_not_active(monkeypatch):
    session = DwarfSession(Settings())
    session.simulation = False

    async def noop(self, *args, **kwargs):
        return None

    session._ensure_ws = types.MethodType(noop, session)

    captured: list[tuple[int, int]] = []

    async def fake_send_and_check(
        self, module_id, command_id, request, *, timeout=10.0, expected_responses=None
    ):
        captured.append((module_id, command_id))
        return None

    session._send_and_check = types.MethodType(fake_send_and_check, session)

    session._joystick_active = False
    session._manual_axis_rates = {0: 0.0, 1: 0.0}

    await session.telescope_stop_axis(0)

    assert captured == []
