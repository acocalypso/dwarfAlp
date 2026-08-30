import asyncio
import math
import time
import types
from typing import Any, Dict

import pytest

from dwarf_alpaca.config.settings import Settings
from dwarf_alpaca.dwarf import session as session_module
from dwarf_alpaca.dwarf.session import DwarfSession
from dwarf_alpaca.dwarf.ws_client import DwarfCommandError
from dwarf_alpaca.proto import astro_pb2, protocol_pb2
from dwarf_alpaca.proto.dwarf_messages import (
    TYPE_NOTIFICATION,
    WsPacket,
)
from dwarf_alpaca.proto.notify_pb2 import (
    AstroAutoFocusState,
    AstroCalibrationState,
    CalibrationResult,
    OneClickGotoState,
)
from dwarf_alpaca.proto.task_center_pb2 import ResEnterCamera, ResSwitchShootingMode


def _settings(**overrides: Any) -> Settings:
    return Settings(site_latitude=48.1372, site_longitude=11.5756, **overrides)


async def _noop_method(self, *args, **kwargs):
    return None


async def _begin_via_send_request(
    self, module_id, command_id, request, response_cls
):
    response = await self._send_request(
        module_id, command_id, request, response_cls, timeout=10.0
    )
    future = asyncio.get_running_loop().create_future()
    future.set_result(response)
    return future


def _stub_one_click_transport(session: DwarfSession) -> None:
    session._prepare_one_click_goto_mode = types.MethodType(_noop_method, session)
    session._begin_request = types.MethodType(_begin_via_send_request, session)


@pytest.mark.asyncio
@pytest.mark.parametrize("model", ["dwarf2", "dwarf3", "dwarfmini"])
async def test_explicit_calibration_uses_shared_v3_command(model: str) -> None:
    session = DwarfSession(_settings(dwarf_device_model=model))
    session.simulation = False
    calls: list[tuple[int, int]] = []
    requests: list[Any] = []
    captured_expected_responses = None

    async def fake_send_and_check(
        self, module_id, command_id, request, *, timeout=10.0, expected_responses=None
    ):
        nonlocal captured_expected_responses
        calls.append((module_id, command_id))
        requests.append(request)
        captured_expected_responses = expected_responses

    session._send_and_check = types.MethodType(fake_send_and_check, session)

    await session.ensure_calibration()

    assert calls == [
        (
            protocol_pb2.ModuleId.MODULE_FOCUS,
            protocol_pb2.DwarfCMD.CMD_FOCUS_START_ASTRO_AUTO_FOCUS,
        ),
        (
            protocol_pb2.ModuleId.MODULE_ASTRO,
            protocol_pb2.DwarfCMD.CMD_ASTRO_START_CALIBRATION,
        ),
    ]
    calibration_request = requests[1]
    assert calibration_request.lon == pytest.approx(11.5756)
    assert calibration_request.lat == pytest.approx(48.1372)
    assert captured_expected_responses == {
        (
            protocol_pb2.ModuleId.MODULE_NOTIFY,
            protocol_pb2.DwarfCMD.CMD_NOTIFY_CALIBRATION_RESULT,
        ): CalibrationResult,
    }
    assert session.get_calibration_status()["status"] == "successful"


@pytest.mark.asyncio
async def test_calibration_notifications_record_progress_and_success() -> None:
    session = DwarfSession(_settings(dwarf_device_model="dwarfmini"))
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
async def test_one_click_goto_notification_is_decoded() -> None:
    session = DwarfSession(_settings(dwarf_device_model="dwarf3"))
    session.simulation = False
    session._one_click_goto_active = True
    session._record_goto(5.5, 22.0)
    session._mark_goto_pending(kind="dso", target_name="M42")
    notification = OneClickGotoState()
    notification.astro_goto_state.state = 1
    packet = WsPacket(
        module_id=protocol_pb2.ModuleId.MODULE_NOTIFY,
        cmd=protocol_pb2.DwarfCMD.CMD_NOTIFY_STATE_ASTRO_ONE_CLICK_GOTO,
        type=TYPE_NOTIFICATION,
        data=notification.SerializeToString(),
    )

    await session._handle_notification(packet)

    assert session._goto_waiting_for_tracking is True


@pytest.mark.asyncio
async def test_v3_one_click_tracking_envelope_completes_slew() -> None:
    session = DwarfSession(_settings(dwarf_device_model="dwarf3"))
    session.simulation = False
    session._one_click_goto_active = True
    session._record_goto(18.3133333338, -13.80666667)
    session._mark_goto_pending(kind="dso", target_name="Custom")

    # Exact CMD 15233 payloads captured from DWARF 3 firmware on 2026-08-02:
    # field 3 is the GoTo phase (running -> plate solving -> stopped).
    for payload_hex in (
        "1a0a08011206437573746f6d",
        "1a0a08041206437573746f6d",
        "1a0a08031206437573746f6d",
    ):
        packet = WsPacket(
            module_id=protocol_pb2.ModuleId.MODULE_NOTIFY,
            cmd=protocol_pb2.DwarfCMD.CMD_NOTIFY_STATE_ASTRO_ONE_CLICK_GOTO,
            type=TYPE_NOTIFICATION,
            data=bytes.fromhex(payload_hex),
        )
        await session._handle_notification(packet)

    assert session._goto_pending is True
    assert session._goto_waiting_for_tracking is True

    # Field 4 tracking state RUNNING is the terminal successful-slew signal.
    tracking_packet = WsPacket(
        module_id=protocol_pb2.ModuleId.MODULE_NOTIFY,
        cmd=protocol_pb2.DwarfCMD.CMD_NOTIFY_STATE_ASTRO_ONE_CLICK_GOTO,
        type=TYPE_NOTIFICATION,
        data=bytes.fromhex("220a08011206437573746f6d"),
    )
    await session._handle_notification(tracking_packet)

    assert session._goto_pending is False
    assert session._goto_result == "success"
    assert session._goto_reason == "one_click_tracking_running:Custom"
    assert session._goto_completion_event.is_set()
    assert session._one_click_goto_active is False


@pytest.mark.asyncio
async def test_first_slew_matches_app_one_click_goto_payload() -> None:
    session = DwarfSession(_settings(dwarf_device_model="dwarfmini"))
    session.simulation = False

    async def noop(self, *args, **kwargs):
        return None

    session._ensure_ws = types.MethodType(noop, session)
    captured: dict[str, Any] = {}

    async def fake_send_and_check(self, *args, **kwargs):
        return None

    async def fake_send_request(
        self, module_id, command_id, request, response_cls, **kwargs
    ):
        captured.update(
            module_id=module_id,
            command_id=command_id,
            request=request,
            response_cls=response_cls,
        )
        return response_cls()

    session._send_and_check = types.MethodType(fake_send_and_check, session)
    session._send_request = types.MethodType(fake_send_request, session)
    _stub_one_click_transport(session)

    await session.telescope_slew_to_coordinates(
        5.5881, -5.3911, target_name="M42"
    )

    request = captured["request"]
    assert captured["module_id"] == protocol_pb2.ModuleId.MODULE_ASTRO
    assert captured["command_id"] == 11013
    assert captured["response_cls"] is astro_pb2.ResOneClickGoto
    assert request.ra == pytest.approx(5.5881)  # App sends Atlas RA in hours.
    assert request.dec == pytest.approx(-5.3911)
    assert request.target_name == "M42"
    assert request.lon == pytest.approx(11.5756)
    assert request.lat == pytest.approx(48.1372)
    assert request.shooting_mode == 2
    assert request.goto_only is False
    assert request.HasField("rotation") is False


@pytest.mark.asyncio
async def test_one_click_goto_preparation_matches_captured_app_sequence() -> None:
    session = DwarfSession(_settings(dwarf_device_model="dwarfmini"))
    session.simulation = False
    calls: list[tuple[int, int, Any]] = []

    async def fake_send_request(
        self, module_id, command_id, request, response_cls, **kwargs
    ):
        calls.append((module_id, command_id, request))
        if command_id == 16402:
            return ResSwitchShootingMode(code=protocol_pb2.OK, shooting_mode_id=8)
        return ResEnterCamera(code=protocol_pb2.OK, shooting_mode_id=8)

    async def fake_send_and_check(
        self, module_id, command_id, request, **kwargs
    ):
        calls.append((module_id, command_id, request))
        return None

    session._send_request = types.MethodType(fake_send_request, session)
    session._send_and_check = types.MethodType(fake_send_and_check, session)

    await session._prepare_one_click_goto_mode()

    assert [command for _, command, _ in calls] == [16402, 16404, 10050, 12036]
    assert calls[0][2].mode == 8
    assert calls[1][2].client_param.encode_type == 1
    assert calls[2][2].level == 1
    assert calls[3][2].level == 1


@pytest.mark.asyncio
async def test_one_click_goto_final_error_is_handled_asynchronously() -> None:
    session = DwarfSession(_settings(dwarf_device_model="dwarfmini"))
    session.simulation = False
    loop = asyncio.get_running_loop()
    response_future = loop.create_future()

    async def fake_begin_request(self, *args, **kwargs):
        return response_future

    session._begin_request = types.MethodType(fake_begin_request, session)

    await session._start_one_click_goto_command(22.724, -8.088, "Unknown")
    assert session._goto_pending is True

    response_future.set_result(
        astro_pb2.ResOneClickGoto(step=30, code=-11504, all_end=True)
    )
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert session._goto_pending is False
    assert session._goto_result == "failed"
    assert session._goto_reason == "one_click_code_-11504"
    assert session.get_calibration_status()["status"] == "failed"


@pytest.mark.asyncio
async def test_calibration_trace_counts_known_and_unknown_notifications() -> None:
    session = DwarfSession(_settings(dwarf_device_model="dwarfmini"))
    session.simulation = False
    session._begin_calibration_trace(latitude=48.1372, longitude=11.5756)

    unknown_packet = WsPacket(
        module_id=protocol_pb2.ModuleId.MODULE_NOTIFY,
        cmd=15999,
        type=TYPE_NOTIFICATION,
        data=b"\x08\x01",
    )
    await session._handle_notification(unknown_packet)

    assert session._calibration_trace_notifications == 1
    assert session._calibration_trace_started is not None
    session._finish_calibration_trace(outcome="test")
    assert session._calibration_trace_started is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "command_id",
    [
        protocol_pb2.DwarfCMD.CMD_NOTIFY_ASTRO_AUTO_FOCUS_STATE,
        protocol_pb2.DwarfCMD.CMD_NOTIFY_ASTRO_AUTO_FOCUS_FAST_STATE,
    ],
)
async def test_autofocus_completion_notifications_are_shared_v3(command_id: int) -> None:
    session = DwarfSession(_settings(dwarf_device_model="dwarf2"))
    session.simulation = False
    notification = AstroAutoFocusState(state=3)
    packet = WsPacket(
        module_id=protocol_pb2.ModuleId.MODULE_NOTIFY,
        cmd=command_id,
        type=TYPE_NOTIFICATION,
        data=notification.SerializeToString(),
    )

    await session._handle_notification(packet)

    assert session._autofocus_completion_event.is_set()
    assert session.get_calibration_status()["status"] == "autofocus completed"


@pytest.mark.asyncio
async def test_calibration_timeout_is_not_reported_as_successful() -> None:
    session = DwarfSession(_settings(dwarf_device_model="dwarfmini"))
    session.simulation = False

    async def timeout(self, module_id, command_id, *args, **kwargs):
        if command_id == protocol_pb2.DwarfCMD.CMD_ASTRO_START_CALIBRATION:
            raise TimeoutError
        return None

    session._send_and_check = types.MethodType(timeout, session)

    with pytest.raises(TimeoutError):
        await session.ensure_calibration()

    outcome = session.get_calibration_status()
    assert outcome["status"] == "not confirmed"
    assert "timeout" in outcome["detail"].lower()


@pytest.mark.asyncio
async def test_calibration_requires_observer_location_before_autofocus() -> None:
    session = DwarfSession(Settings(dwarf_device_model="dwarfmini"))
    session.simulation = False

    with pytest.raises(RuntimeError, match="latitude and longitude"):
        await session.ensure_calibration()

    outcome = session.get_calibration_status()
    assert outcome["status"] == "location required"


def test_auto_calibration_is_enabled_for_requested_slews_by_default() -> None:
    settings = _settings()

    assert settings.auto_calibrate_on_slew is True
    assert settings.calibration_timeout_seconds >= 300.0
    assert settings.calibration_wait_for_slew_seconds >= (
        settings.calibration_autofocus_timeout_seconds
        + settings.calibration_timeout_seconds
    )


@pytest.mark.asyncio
async def test_telescope_slew_retries_one_click_goto_after_failure(monkeypatch):
    session = DwarfSession(_settings(dwarf_device_model="dwarf3"))
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
        if command_id == protocol_pb2.DwarfCMD.CMD_ASTRO_START_ONE_CLICK_GOTO_DSO:
            goto_attempts += 1
            if goto_attempts == 1:
                raise DwarfCommandError(module_id, command_id, protocol_pb2.CODE_ASTRO_GOTO_FAILED)

    session._send_and_check = types.MethodType(fake_send_and_check, session)

    async def fake_send_request(self, module_id, command_id, request, response_cls, **kwargs):
        await fake_send_and_check(self, module_id, command_id, request, **kwargs)
        return response_cls()

    session._send_request = types.MethodType(fake_send_request, session)
    _stub_one_click_transport(session)

    async def instant_sleep(_duration):
        return None

    monkeypatch.setattr(session_module.asyncio, "sleep", instant_sleep)

    result = await session.telescope_slew_to_coordinates(14.6817, 69.5667)

    assert result == (14.6817, 69.5667)
    assert actions.count(protocol_pb2.DwarfCMD.CMD_ASTRO_START_CALIBRATION) == 0
    assert actions.count(protocol_pb2.DwarfCMD.CMD_ASTRO_START_ONE_CLICK_GOTO_DSO) == 2
    assert protocol_pb2.DwarfCMD.CMD_ASTRO_STOP_ONE_CLICK_GOTO in actions


@pytest.mark.asyncio
async def test_telescope_slew_retries_after_busy(monkeypatch):
    settings = _settings()
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
        if command_id == protocol_pb2.DwarfCMD.CMD_ASTRO_START_ONE_CLICK_GOTO_DSO:
            if busy_state["value"]:
                busy_state["value"] = False
                raise DwarfCommandError(module_id, command_id, -11501)
        return None

    session._send_and_check = types.MethodType(fake_send_and_check, session)

    async def fake_send_request(self, module_id, command_id, request, response_cls, **kwargs):
        await fake_send_and_check(self, module_id, command_id, request, **kwargs)
        return response_cls()

    session._send_request = types.MethodType(fake_send_request, session)
    _stub_one_click_transport(session)

    sleep_calls: list[float] = []

    async def instant_sleep(duration):
        sleep_calls.append(duration)
        return None

    monkeypatch.setattr(session_module.asyncio, "sleep", instant_sleep)

    result = await session.telescope_slew_to_coordinates(1.0, 2.0)

    assert result == (1.0, 2.0)
    assert sleep_calls == [0.2]

    goto_calls = [
        cmd for cmd in actions if cmd[1] == protocol_pb2.DwarfCMD.CMD_ASTRO_START_ONE_CLICK_GOTO_DSO
    ]
    assert len(goto_calls) == 2
    assert (
        protocol_pb2.ModuleId.MODULE_ASTRO,
        protocol_pb2.DwarfCMD.CMD_ASTRO_STOP_ONE_CLICK_GOTO,
    ) in actions

    calibration_calls = [
        cmd for cmd in actions if cmd[1] == protocol_pb2.DwarfCMD.CMD_ASTRO_START_CALIBRATION
    ]
    assert calibration_calls == []

    assert len(stop_calls) >= 4
    assert {axis for axis, _ in stop_calls} == {0, 1}


@pytest.mark.asyncio
async def test_telescope_slew_raises_after_repeated_busy(monkeypatch):
    settings = _settings()
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
        if command_id == protocol_pb2.DwarfCMD.CMD_ASTRO_START_ONE_CLICK_GOTO_DSO:
            raise DwarfCommandError(module_id, command_id, -11501)
        return None

    session._send_and_check = types.MethodType(fake_send_and_check, session)

    async def fake_send_request(self, module_id, command_id, request, response_cls, **kwargs):
        await fake_send_and_check(self, module_id, command_id, request, **kwargs)
        return response_cls()

    session._send_request = types.MethodType(fake_send_request, session)
    _stub_one_click_transport(session)

    async def instant_sleep(duration):
        return None

    monkeypatch.setattr(session_module.asyncio, "sleep", instant_sleep)

    with pytest.raises(DwarfCommandError) as exc:
        await session.telescope_slew_to_coordinates(3.0, -1.0)

    assert exc.value.code == -11501

    goto_calls = [
        cmd for cmd in actions if cmd[1] == protocol_pb2.DwarfCMD.CMD_ASTRO_START_ONE_CLICK_GOTO_DSO
    ]
    assert len(goto_calls) == 2
    assert (
        protocol_pb2.ModuleId.MODULE_ASTRO,
        protocol_pb2.DwarfCMD.CMD_ASTRO_STOP_ONE_CLICK_GOTO,
    ) in actions

    calibration_calls = [
        cmd for cmd in actions if cmd[1] == protocol_pb2.DwarfCMD.CMD_ASTRO_START_CALIBRATION
    ]
    assert calibration_calls == []


@pytest.mark.asyncio
async def test_telescope_slew_refreshes_calibration_after_expiry(monkeypatch):
    settings = _settings()
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

    async def fake_send_request(self, module_id, command_id, request, response_cls, **kwargs):
        actions.append((module_id, command_id))
        return response_cls()

    session._send_request = types.MethodType(fake_send_request, session)
    _stub_one_click_transport(session)

    await session.telescope_slew_to_coordinates(1.2, -3.4)

    assert (
        protocol_pb2.ModuleId.MODULE_ASTRO,
        protocol_pb2.DwarfCMD.CMD_ASTRO_START_ONE_CLICK_GOTO_DSO,
    ) in actions

    session._last_calibration_time = time.time()
    session._last_calibration_ip = settings.dwarf_ap_ip

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

    assert (
        protocol_pb2.ModuleId.MODULE_ASTRO,
        protocol_pb2.DwarfCMD.CMD_ASTRO_START_ONE_CLICK_GOTO_DSO,
    ) in actions


@pytest.mark.asyncio
async def test_telescope_slew_falls_back_when_firmware_requires_calibration():
    settings = _settings()
    settings.auto_calibrate_on_slew = True
    session = DwarfSession(settings)
    session.simulation = False
    session._last_calibration_time = time.time()
    session._last_calibration_ip = settings.dwarf_ap_ip

    async def noop(self, *args, **kwargs):
        return None

    session._ensure_ws = types.MethodType(noop, session)
    _stub_one_click_transport(session)
    preparation: list[str] = []

    async def prepare_autofocus(self):
        preparation.append("autofocus")
        return 52.0, 13.0

    async def prepare_mode(self):
        preparation.append("mode")

    session._prepare_calibration_autofocus = types.MethodType(
        prepare_autofocus, session
    )
    session._prepare_one_click_goto_mode = types.MethodType(prepare_mode, session)

    actions: list[int] = []

    async def fake_send_and_check(
        self, module_id, command_id, request, *, timeout=10.0, expected_responses=None
    ):
        actions.append(command_id)
        if command_id == protocol_pb2.DwarfCMD.CMD_ASTRO_START_GOTO_DSO:
            raise DwarfCommandError(
                module_id,
                command_id,
                protocol_pb2.CODE_ASTRO_NEED_CALIBRATION,
            )
        return None

    session._send_and_check = types.MethodType(fake_send_and_check, session)

    async def fake_send_request(self, module_id, command_id, request, response_cls, **kwargs):
        await fake_send_and_check(self, module_id, command_id, request, **kwargs)
        return response_cls()

    session._send_request = types.MethodType(fake_send_request, session)

    result = await session.telescope_slew_to_coordinates(5.5, -12.0, target_name="M42")

    assert result == (5.5, -12.0)
    assert preparation == ["autofocus", "mode"]
    assert actions.count(protocol_pb2.DwarfCMD.CMD_ASTRO_START_GOTO_DSO) == 1
    assert (
        actions.count(protocol_pb2.DwarfCMD.CMD_ASTRO_START_ONE_CLICK_GOTO_DSO)
        == 1
    )
    assert session._last_calibration_time is None
    assert session._last_calibration_ip is None


@pytest.mark.asyncio
async def test_telescope_slew_uses_configured_timeout(monkeypatch):
    settings = _settings()
    settings.goto_command_timeout_seconds = 42.5
    session = DwarfSession(settings)
    session.simulation = False
    session._last_calibration_time = time.time()
    session._last_calibration_ip = settings.dwarf_ap_ip

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

    async def fake_send_request(self, module_id, command_id, request, response_cls, **kwargs):
        captured_timeout["value"] = kwargs["timeout"]
        return response_cls()

    session._send_request = types.MethodType(fake_send_request, session)

    await session.telescope_slew_to_coordinates(1.2, 3.4)

    assert "value" in captured_timeout
    assert captured_timeout["value"] == pytest.approx(settings.goto_command_timeout_seconds)


@pytest.mark.asyncio
async def test_acquire_telescope_does_not_schedule_calibration(monkeypatch):
    session = DwarfSession(_settings())
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
    session = DwarfSession(_settings())
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
    session = DwarfSession(_settings())
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
    settings = _settings()
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
    session = DwarfSession(_settings())
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
    assert entry["vector_length"] == pytest.approx(1.5 / 30.0)
    assert entry["speed"] is None
    assert session._manual_axis_rates[0] == pytest.approx(1.5)
    assert session._joystick_active is True


@pytest.mark.asyncio
async def test_telescope_move_axis_clamps_speed(monkeypatch):
    session = DwarfSession(_settings())
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
    assert entry["vector_length"] == pytest.approx(1.0)
    assert entry["speed"] is None
    assert entry["vector_length"] == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_telescope_move_axis_combines_axes(monkeypatch):
    session = DwarfSession(_settings())
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
    assert captured[-1]["vector_length"] == pytest.approx(math.hypot(5.0, 5.0) / 30.0)
    assert captured[-1]["speed"] is None


@pytest.mark.asyncio
async def test_telescope_stop_axis_sends_stop_when_idle(monkeypatch):
    session = DwarfSession(_settings())
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
    session = DwarfSession(_settings())
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
