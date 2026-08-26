import asyncio
import time
import types
from datetime import datetime

import numpy as np
import pytest

from dwarf_alpaca.config.settings import Settings
from dwarf_alpaca.dwarf.session import (
    CaptureBusyError,
    CaptureConfigurationError,
    CapturePhase,
    DwarfSession,
    _decode_v3_device_config_payload,
)
from dwarf_alpaca.dwarf.ws_client import DwarfCommandError
from dwarf_alpaca.proto import astro_pb2, protocol_pb2
from dwarf_alpaca.proto.dwarf_messages import (
    TYPE_NOTIFICATION,
    ComResponse,
    ResNotifyTemperature,
    WsPacket,
)
from dwarf_alpaca.proto.notify_pb2 import (
    CmosTemperature,
    ProgressCaptureRawLiveStacking,
    SwitchShootingMode,
)
from dwarf_alpaca.proto.task_center_pb2 import (
    ResEnterCamera,
    ResNotifyTaskState,
    ResSwitchShootingMode,
    ResSwitchShootingTech,
)


@pytest.mark.asyncio
async def test_v3_capture_enters_deep_sky_mode_before_opening_camera(monkeypatch):
    session = DwarfSession(Settings(force_simulation=True, dwarf_device_model="dwarf3"))
    session.simulation = False
    calls: list[tuple[int, int, object]] = []

    async def fake_send_request(module_id, command_id, request, _response_cls, **_kwargs):
        calls.append((module_id, command_id, request))
        if command_id == 16402:
            response = ResSwitchShootingMode()
            response.code = protocol_pb2.OK
            response.shooting_mode_id = 8
            return response
        if command_id == 16404:
            response = ResEnterCamera(code=protocol_pb2.OK, shooting_mode_id=8)
            return response
        if command_id == 16403:
            response = ResSwitchShootingTech()
            response.code = protocol_pb2.OK
            response.shooting_tech_id = 2
            return response
        raise AssertionError(f"unexpected command {command_id}")

    async def fake_send_and_check(module_id, command_id, request, **_kwargs):
        calls.append((module_id, command_id, request))

    monkeypatch.setattr(session, "_send_request", fake_send_request)
    monkeypatch.setattr(session, "_send_and_check", fake_send_and_check)

    await session._enter_v3_astro_mode()

    assert [command for _, command, _ in calls] == [16402, 16404, 16403, 10050]
    assert calls[0][2].mode == 8
    assert calls[1][2].client_param.encode_type == 1
    assert calls[2][2].tech == 2
    assert calls[3][2].level == 1


@pytest.mark.asyncio
async def test_v3_capture_accepts_legacy_mode_two_confirmation(monkeypatch):
    session = DwarfSession(Settings(force_simulation=True, dwarf_device_model="dwarf3"))
    session.simulation = False

    async def fake_send_request(_module_id, command_id, _request, _response_cls, **_kwargs):
        if command_id == 16402:
            return ResSwitchShootingMode(code=protocol_pb2.OK, shooting_mode_id=8)
        if command_id == 16404:
            return ResEnterCamera(code=protocol_pb2.OK, shooting_mode_id=2)
        return ResSwitchShootingTech(code=protocol_pb2.OK, shooting_tech_id=2)

    async def fake_send_and_check(*_args, **_kwargs):
        return None

    monkeypatch.setattr(session, "_send_request", fake_send_request)
    monkeypatch.setattr(session, "_send_and_check", fake_send_and_check)

    await session._enter_v3_astro_mode()


@pytest.mark.asyncio
async def test_v3_capture_rejects_failed_deep_sky_mode_confirmation(monkeypatch):
    session = DwarfSession(Settings(force_simulation=True, dwarf_device_model="dwarf3"))
    session.simulation = False

    async def fake_send_request(_module_id, _command_id, _request, _response_cls, **_kwargs):
        return ResSwitchShootingMode(code=protocol_pb2.OK, shooting_mode_id=1)

    monkeypatch.setattr(session, "_send_request", fake_send_request)

    with pytest.raises(CaptureConfigurationError, match="did not select astronomy mode"):
        await session._enter_v3_astro_mode()


@pytest.mark.asyncio
async def test_overlapping_capture_is_rejected_without_cancelling_first():
    session = DwarfSession(Settings(force_simulation=True))
    first_task = asyncio.create_task(asyncio.sleep(10))
    session.camera_state.capture_task = first_task
    session.camera_state.capture_phase = CapturePhase.EXPOSING

    with pytest.raises(CaptureBusyError):
        await session.camera_start_exposure(1.0, True)

    assert not first_task.cancelled()
    first_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first_task


@pytest.mark.asyncio
async def test_mini_v3_astro_preset_is_discovered_and_confirmed(monkeypatch):
    session = DwarfSession(Settings(force_simulation=True, dwarf_device_model="dwarfmini"))
    session.simulation = False
    session._params_config = {}
    session.camera_state.duration = 1.0
    session.camera_state.requested_gain = 60
    session._v3_astro_param_catalog = {
        "cameraParams": [{"cameraId": 0, "specialParams": {
            "exp": {"paramId": 0x201000000000001, "values": [{"name": "1", "value": 120}]},
            "gain": {"paramId": 0x201000000000002, "values": [60]},
        }}]
    }
    calls: list[tuple[int, str]] = []
    adjusted: list[tuple[int, int, int, int]] = []

    async def fake_send_request(_module, command, request, _response_cls, **_kwargs):
        if command == protocol_pb2.DwarfCMD.CMD_ASTRO_GET_QUICK_SET_LIST:
            response = astro_pb2.ResGetQuickSetList()
            entry = response.quick_set_list.add()
            entry.info_id = "0|0|15|60|1|null"
            return response
        raise AssertionError(f"unexpected command {command}")

    async def fake_send_and_check(module, command, request, **_kwargs):
        adjusted.append((module, command, request.param_id, request.value))

    monkeypatch.setattr(session, "_send_request", fake_send_request)
    monkeypatch.setattr(session, "_send_and_check", fake_send_and_check)

    await session._ensure_exposure_settings(1.0)
    await session._ensure_gain_settings()
    await session._configure_astro_capture(frames=2, binning=(1, 1))

    assert calls == []
    assert session.camera_state.applied_duration == 1.0
    assert session.camera_state.applied_gain_value == 60
    assert session.camera_state.applied_bin == (1, 1)
    assert session.camera_state.applied_frame_count == 2
    assert adjusted == [
        (15, 16700, 0x201000000000001, 120),
        (15, 16701, 0x201000000000002, 60),
        (15, 16703, 0x202000000000010, 2),
    ]


@pytest.mark.asyncio
async def test_dwarf3_v3_astro_frame_count_uses_dedicated_adjust_param(monkeypatch):
    session = DwarfSession(Settings(force_simulation=True, dwarf_device_model="dwarf3"))
    session.simulation = False
    session._params_config = {}
    session.camera_state.duration = 1.0
    session.camera_state.requested_gain = 60
    session._v3_astro_param_catalog = {
        "cameraParams": [{"cameraId": 0, "specialParams": {
            "exp": {"paramId": 0x201000000000001, "values": [{"name": "1", "value": 120}]},
            "gain": {"paramId": 0x201000000000002, "values": [60]},
        }}]
    }
    adjusted: list[tuple[int, int, int, int]] = []

    async def fake_send_request(_module, command, request, _response_cls, **_kwargs):
        if command == protocol_pb2.DwarfCMD.CMD_ASTRO_GET_QUICK_SET_LIST:
            response = astro_pb2.ResGetQuickSetList()
            entry = response.quick_set_list.add()
            entry.info_id = "0|0|1|60|999|null"
            return response
        raise AssertionError(f"unexpected command {command}")

    async def fake_send_and_check(module, command, request, **_kwargs):
        adjusted.append((module, command, request.param_id, request.value))

    monkeypatch.setattr(session, "_send_request", fake_send_request)
    monkeypatch.setattr(session, "_send_and_check", fake_send_and_check)

    await session._ensure_exposure_settings(1.0)
    await session._ensure_gain_settings()
    await session._configure_astro_capture(frames=1, binning=(1, 1))

    assert adjusted == [
        (15, 16700, 0x201000000000001, 120),
        (15, 16701, 0x201000000000002, 60),
        (15, 16703, 0x202000000000010, 1),
    ]
    assert session.camera_state.applied_frame_count == 1


@pytest.mark.asyncio
async def test_dwarf3_v3_astro_preset_accepts_firmware_zero_placeholder(monkeypatch):
    session = DwarfSession(Settings(force_simulation=True, dwarf_device_model="dwarf3"))
    session.simulation = False

    async def fake_send_request(_module, command, _request, _response_cls, **_kwargs):
        assert command == protocol_pb2.DwarfCMD.CMD_ASTRO_GET_QUICK_SET_LIST
        response = astro_pb2.ResGetQuickSetList()
        entry = response.quick_set_list.add()
        entry.exp_name = "1"
        entry.gain = 120
        entry.info_id = "0|0|1|120|0|null"
        return response

    monkeypatch.setattr(session, "_send_request", fake_send_request)

    presets = await session._get_v3_astro_presets()

    assert len(presets) == 1
    assert presets[0].exposure_s == 1.0
    assert presets[0].gain == 120
    assert presets[0].frame_count == 1


@pytest.mark.asyncio
async def test_mini_astro_start_embeds_selected_duoband_filter(monkeypatch):
    session = DwarfSession(Settings(force_simulation=True, dwarf_device_model="dwarfmini"))
    session.simulation = False
    await session._get_filter_options()
    session.camera_state.filter_index = 1
    session.camera_state.filter_name = "Duo-Band"
    captured: dict[str, object] = {}

    async def fake_begin_request(module_id, command_id, request, _response_cls):
        captured["module_id"] = module_id
        captured["command_id"] = command_id
        captured["request"] = astro_pb2.ReqCaptureRawLiveStacking.FromString(
            request.SerializeToString()
        )
        response = ComResponse()
        response.code = protocol_pb2.OK
        future = asyncio.get_running_loop().create_future()
        future.set_result(response)
        return future

    monkeypatch.setattr(session, "_begin_request", fake_begin_request)

    code = await session._start_astro_capture(timeout=5.0)

    assert code == protocol_pb2.OK
    request = captured["request"]
    assert isinstance(request, astro_pb2.ReqCaptureRawLiveStacking)
    assert request.ir_index == 2
    assert request.force_start is True
    assert session.camera_state.applied_filter_name == "Duo-Band"


@pytest.mark.asyncio
async def test_dwarf3_astro_start_embeds_selected_filter(monkeypatch):
    session = DwarfSession(Settings(force_simulation=True, dwarf_device_model="dwarf3"))
    session.simulation = False
    await session._get_filter_options()
    session.camera_state.filter_index = 2
    session.camera_state.filter_name = "Duo-Band Filter"
    captured: dict[str, object] = {}

    async def fake_begin_request(_module_id, _command_id, request, _response_cls):
        captured["request"] = astro_pb2.ReqCaptureRawLiveStacking.FromString(
            request.SerializeToString()
        )
        response = ComResponse()
        response.code = protocol_pb2.OK
        future = asyncio.get_running_loop().create_future()
        future.set_result(response)
        return future

    monkeypatch.setattr(session, "_begin_request", fake_begin_request)

    await session._start_astro_capture(timeout=5.0)

    request = captured["request"]
    assert isinstance(request, astro_pb2.ReqCaptureRawLiveStacking)
    assert request.ir_index == 2
    assert request.force_start is True
    assert session.camera_state.applied_filter_name == "Duo-Band Filter"


@pytest.mark.asyncio
async def test_dwarf2_astro_start_uses_v3_sentinel_payload(monkeypatch):
    session = DwarfSession(Settings(force_simulation=True, dwarf_device_model="dwarf2"))
    session.simulation = False
    captured: dict[str, object] = {}

    async def fake_begin_request(_module_id, _command_id, request, _response_cls):
        captured["request"] = astro_pb2.ReqCaptureRawLiveStacking.FromString(
            request.SerializeToString()
        )
        response = ComResponse()
        response.code = protocol_pb2.OK
        future = asyncio.get_running_loop().create_future()
        future.set_result(response)
        return future

    monkeypatch.setattr(session, "_begin_request", fake_begin_request)

    await session._start_astro_capture(timeout=5.0)

    request = captured["request"]
    assert isinstance(request, astro_pb2.ReqCaptureRawLiveStacking)
    assert request.ir_index == -1
    assert request.force_start is False
    assert request.SerializeToString() == b"\x08\xff\xff\xff\xff\xff\xff\xff\xff\xff\x01"


@pytest.mark.asyncio
@pytest.mark.parametrize("model", ["dwarfmini", "dwarf3"])
async def test_filtered_v3_start_does_not_force_after_recent_goto(monkeypatch, model):
    session = DwarfSession(Settings(force_simulation=True, dwarf_device_model=model))
    session.simulation = False
    captured: dict[str, object] = {}

    async def fake_begin_request(_module_id, _command_id, request, _response_cls):
        captured["request"] = astro_pb2.ReqCaptureRawLiveStacking.FromString(
            request.SerializeToString()
        )
        response = ComResponse()
        response.code = protocol_pb2.OK
        future = asyncio.get_running_loop().create_future()
        future.set_result(response)
        return future

    monkeypatch.setattr(session, "_begin_request", fake_begin_request)
    monkeypatch.setattr(session, "_has_recent_goto", lambda: True)

    await session._start_astro_capture(timeout=5.0)

    request = captured["request"]
    assert isinstance(request, astro_pb2.ReqCaptureRawLiveStacking)
    assert request.force_start is False


@pytest.mark.asyncio
async def test_astro_baseline_does_not_scan_ftp(monkeypatch):
    session = DwarfSession(Settings(force_simulation=True, dwarf_device_model="dwarfmini"))
    session.simulation = False

    async def fail_scan(*_args, **_kwargs):
        raise AssertionError("astro StartExposure must not block on an FTP scan")

    monkeypatch.setattr(type(session._ftp_client), "get_latest_photo_entry", fail_scan)

    await session._refresh_capture_baseline(capture_kind="astro")

    assert session.camera_state.pending_ftp_baseline is None


@pytest.mark.asyncio
async def test_abort_during_configuration_prevents_late_capture_start(monkeypatch):
    session = DwarfSession(Settings(force_simulation=True, dwarf_device_model="dwarfmini"))
    session.simulation = False
    state = session.camera_state
    baseline_entered = asyncio.Event()
    release_baseline = asyncio.Event()
    starts: list[bool] = []

    async def noop(*_args, **_kwargs):
        return None

    async def ensure_dark(*_args, **_kwargs):
        return True

    async def blocking_baseline(*_args, **_kwargs):
        baseline_entered.set()
        await release_baseline.wait()

    async def fake_start(*, timeout: float):
        starts.append(True)
        return protocol_pb2.OK

    monkeypatch.setattr(session, "_ensure_ws", noop)
    monkeypatch.setattr(session, "_enter_v3_astro_mode", noop)
    monkeypatch.setattr(session, "_ensure_exposure_settings", noop)
    monkeypatch.setattr(session, "_ensure_gain_settings", noop)
    monkeypatch.setattr(session, "_ensure_selected_filter", noop)
    monkeypatch.setattr(session, "_astro_go_live", noop)
    monkeypatch.setattr(session, "_ensure_dark_library", ensure_dark)
    monkeypatch.setattr(session, "_configure_astro_capture", noop)
    monkeypatch.setattr(session, "_refresh_capture_baseline", blocking_baseline)
    monkeypatch.setattr(session, "_start_astro_capture", fake_start)
    monkeypatch.setattr(session, "_stop_astro_capture", noop)

    start_task = asyncio.create_task(session.camera_start_exposure(1.0, True))
    await baseline_entered.wait()
    await session.camera_abort_exposure()
    release_baseline.set()
    await start_task

    assert starts == []
    assert state.capture_id is None
    assert state.capture_phase == CapturePhase.IDLE


def test_jpeg_decode_returns_nina_compatible_two_dimensional_frame():
    cv2 = pytest.importorskip("cv2")
    import numpy as np

    source = np.zeros((2, 3, 3), dtype=np.uint8)
    source[:, :, 0] = 10
    source[:, :, 1] = 20
    source[:, :, 2] = 30
    ok, encoded = cv2.imencode(".jpg", cv2.cvtColor(source, cv2.COLOR_RGB2BGR))
    assert ok

    decoded = DwarfSession._decode_jpeg(encoded.tobytes())

    assert decoded.dtype == np.uint8
    assert decoded.shape == (2, 3)


def test_album_entry_recency_rejects_old_capture_path():
    started = time.mktime(datetime.strptime("20260802-234815", "%Y%m%d-%H%M%S").timetuple())

    assert not DwarfSession._album_entry_is_recent(
        {
            "filePath": (
                "/DWARF_mini/Astronomy/RESTACKED/"
                "RESTACKED_DWARF_RAW_TELE_M16_Duo-Band_20260729-080242164/stacked.jpg"
            )
        },
        not_before=started,
    )


def test_album_entry_recency_accepts_epoch_milliseconds():
    started = 1_800_000_000.0
    assert DwarfSession._album_entry_is_recent(
        {"filePath": "/new.fits", "modificationTime": int((started + 1) * 1000)},
        not_before=started,
    )


@pytest.mark.asyncio
async def test_temperature_notification_updates_state():
    session = DwarfSession(Settings(force_simulation=True))

    message = ResNotifyTemperature()
    message.code = protocol_pb2.OK
    message.temperature = 123

    packet = WsPacket()
    packet.module_id = protocol_pb2.ModuleId.MODULE_NOTIFY
    packet.cmd = protocol_pb2.DwarfCMD.CMD_NOTIFY_TEMPERATURE
    packet.type = TYPE_NOTIFICATION
    packet.data = message.SerializeToString()

    assert session.camera_state.temperature_c is None
    assert session.camera_state.last_temperature_time is None
    assert session.camera_state.last_temperature_code is None

    await session._handle_notification(packet)

    assert session.camera_state.temperature_c == pytest.approx(123.0)
    assert session.camera_state.last_temperature_time is not None
    assert session.camera_state.last_temperature_code == protocol_pb2.OK


@pytest.mark.asyncio
async def test_v3_temperature2_notification_updates_state() -> None:
    session = DwarfSession(Settings(force_simulation=True))

    message = CmosTemperature(temperature=41, camera_type=0)

    packet = WsPacket()
    packet.module_id = protocol_pb2.ModuleId.MODULE_NOTIFY
    packet.cmd = 15292
    packet.type = TYPE_NOTIFICATION
    packet.data = message.SerializeToString()

    await session._handle_notification(packet)

    assert session.camera_state.temperature_c == pytest.approx(41.0)
    assert session.camera_state.last_temperature_time is not None
    assert session.camera_state.last_temperature_code == protocol_pb2.OK


@pytest.mark.asyncio
async def test_v3_mode_change_notification_updates_session_state() -> None:
    session = DwarfSession(Settings(force_simulation=True))

    message = SwitchShootingMode(state=0, source_mode=8, dst_mode=1)

    packet = WsPacket()
    packet.module_id = protocol_pb2.ModuleId.MODULE_NOTIFY
    packet.cmd = 15267
    packet.type = TYPE_NOTIFICATION
    packet.data = message.SerializeToString()

    await session._handle_notification(packet)

    assert session._v3_mode_change == (0, 8, 1)


@pytest.mark.asyncio
async def test_v3_device_state_notification_updates_session_state() -> None:
    session = DwarfSession(Settings(force_simulation=True))

    message = ResNotifyTaskState(task_id=4)
    message.task_attr.exclusive_mask = 8
    message.task_attr.priority = 1
    message.state.base_state = 2

    packet = WsPacket()
    packet.module_id = protocol_pb2.ModuleId.MODULE_NOTIFY
    packet.cmd = 15261
    packet.type = TYPE_NOTIFICATION
    packet.data = message.SerializeToString()

    await session._handle_notification(packet)

    assert session._v3_device_state_event == 4
    assert session._v3_device_state_mode == 8
    assert session._v3_device_state_detail == 2
    assert session._v3_device_state_path is None


@pytest.mark.asyncio
async def test_astro_progress_stops_when_requested_raw_frames_are_acquired() -> None:
    session = DwarfSession(Settings(force_simulation=True, dwarf_device_model="dwarf3"))
    state = session.camera_state
    state.capture_id = "capture-1"
    state.requested_frame_count = 2

    def progress_packet(*, current: int, stacked: int) -> WsPacket:
        message = ProgressCaptureRawLiveStacking(
            total_count=20,
            update_type=1 if stacked else 0,
            current_count=current,
            camera_type=0,
        )
        packet = WsPacket()
        packet.module_id = protocol_pb2.ModuleId.MODULE_NOTIFY
        packet.cmd = protocol_pb2.DwarfCMD.CMD_NOTIFY_PROGRASS_CAPTURE_RAW_LIVE_STACKING
        packet.type = TYPE_NOTIFICATION
        packet.data = message.SerializeToString()
        return packet

    await session._handle_notification(progress_packet(current=1, stacked=1))

    assert state.progress_total_count == 20
    assert state.progress_current_count == 1
    assert state.progress_stacked_count == 0
    assert not session._capture_frame_complete_event.is_set()

    await session._handle_notification(progress_packet(current=2, stacked=1))

    assert state.progress_current_count == 2
    assert state.progress_stacked_count == 0
    assert session._capture_frame_complete_event.is_set()


@pytest.mark.asyncio
async def test_astro_fetch_stops_on_progress_before_ftp_retrieval_finishes(monkeypatch) -> None:
    session = DwarfSession(Settings(force_simulation=True, dwarf_device_model="dwarf3"))
    session.simulation = False
    state = session.camera_state
    state.capture_id = "capture-1"
    state.capture_mode = "astro"
    state.requested_frame_count = 1
    state.duration = 1.0
    ftp_started = asyncio.Event()
    allow_ftp_finish = asyncio.Event()
    calls: list[str] = []

    async def fake_attempt_ftp(fetch_state) -> bool:
        calls.append("ftp_started")
        ftp_started.set()
        await allow_ftp_finish.wait()
        fetch_state.image = object()
        fetch_state.retrieved_file_path = "/Astronomy/test/frame-1.fit"
        calls.append("ftp_finished")
        return True

    async def fake_stop(*_args, **_kwargs) -> None:
        calls.append("stop")
        allow_ftp_finish.set()

    async def fake_go_live() -> None:
        calls.append("go_live")

    monkeypatch.setattr(session, "_attempt_ftp_capture", fake_attempt_ftp)
    monkeypatch.setattr(session, "_stop_astro_capture", fake_stop)
    monkeypatch.setattr(session, "_astro_go_live", fake_go_live)

    fetch_task = asyncio.create_task(session._fetch_capture(state))
    await ftp_started.wait()
    session._capture_frame_complete_event.set()
    await asyncio.wait_for(fetch_task, timeout=0.5)

    assert calls == ["ftp_started", "stop", "ftp_finished", "go_live"]
    assert state.retrieved_file_path == "/Astronomy/test/frame-1.fit"
    assert state.capture_phase == CapturePhase.READY


@pytest.mark.asyncio
async def test_selected_filter_respected_and_defaulted():
    session = DwarfSession(Settings(force_simulation=True))

    await session.set_filter_position(2)
    state = session.camera_state
    original_index = state.filter_index
    original_label = state.filter_name

    await session._ensure_selected_filter()

    assert state.filter_index == original_index
    assert state.filter_name == original_label

    state.filter_index = 99
    state.filter_name = ""

    await session._ensure_selected_filter()

    assert state.filter_index == 0
    assert state.filter_name


class _DummyHttpClient:
    def __init__(self) -> None:
        self.calls: list[tuple[int, int]] = []

    async def list_album_media_infos(self, *, media_type: int, page_size: int):
        self.calls.append((media_type, page_size))
        return []


@pytest.mark.asyncio
async def test_album_media_type_selection():
    session = DwarfSession(Settings(force_simulation=True))
    dummy_client = _DummyHttpClient()
    session._http_client = dummy_client  # type: ignore[assignment]

    result = await session._get_latest_album_entry(media_type=4)

    assert result == (None, None)
    assert dummy_client.calls == [(4, 1)]


def test_adjust_shoot_parameters_response_is_nonfatal_warning():
    session = DwarfSession(Settings(force_simulation=True, dwarf_device_model="dwarfmini"))
    response = ComResponse()
    response.code = protocol_pb2.CODE_ASTRO_NEED_ADJUST_SHOOT_PARAM

    assert session._validate_astro_start_response(response) == response.code


@pytest.mark.asyncio
async def test_astro_album_download_uses_fits_list(monkeypatch):
    session = DwarfSession(Settings(force_simulation=True, dwarf_device_model="dwarfmini"))
    session.simulation = False
    state = session.camera_state
    state.capture_id = "capture-1"
    calls: list[object] = []

    class DummyHttpClient:
        async def list_astro_fits(self, src_dir: str):
            calls.append(("list", src_dir))
            return [
                {"filePath": "/Astronomy/M11/failed.fit", "isFailed": True},
                {"filePath": "/Astronomy/M11/frame.fit", "isFailed": False},
            ]

        async def fetch_media_file(self, path: str):
            calls.append(("fetch", path))
            return b"fits"

    monkeypatch.setattr(session, "_http_client", DummyHttpClient())
    monkeypatch.setattr(
        session,
        "_decode_capture_content",
        lambda identifier, content: np.zeros((2, 3), dtype="uint16"),
    )

    result = await session._download_album_astro_fits(
        state,
        {"astroImageDetails": {"srcDir": "/Astronomy/M11"}},
    )

    assert result is True
    assert calls == [
        ("list", "/Astronomy/M11"),
        ("fetch", "/Astronomy/M11/frame.fit"),
    ]
    assert state.retrieved_file_path == "/Astronomy/M11/frame.fit"
    assert state.image.shape == (2, 3)


@pytest.mark.asyncio
async def test_camera_start_exposure_simulation_sets_astro_mode():
    session = DwarfSession(Settings(force_simulation=True, dwarf_device_model="dwarf3"))
    state = session.camera_state
    state.requested_frame_count = 3
    state.requested_bin = (2, 2)

    await session.camera_start_exposure(0.1, True)

    assert state.capture_mode == "astro"
    assert state.requested_frame_count == 3
    assert state.requested_bin == (2, 2)
    assert state.image is not None


@pytest.mark.asyncio
async def test_camera_start_exposure_simulation_uses_astro_mode_for_mini_by_default():
    session = DwarfSession(Settings(force_simulation=True, dwarf_device_model="dwarfmini"))
    state = session.camera_state

    await session.camera_start_exposure(0.1, True)

    assert state.capture_mode == "astro"
    assert state.image is not None


@pytest.mark.asyncio
async def test_camera_start_exposure_simulation_can_use_photo_mode_for_mini():
    session = DwarfSession(
        Settings(
            force_simulation=True,
            dwarf_device_model="dwarfmini",
            dwarf_mini_capture_mode="photo",
        )
    )
    state = session.camera_state

    await session.camera_start_exposure(0.1, True)

    assert state.capture_mode == "photo"
    assert state.image is not None


@pytest.mark.asyncio
async def test_camera_start_exposure_accepts_nonfatal_need_goto_warning(monkeypatch):
    session = DwarfSession(Settings(force_simulation=True, dwarf_device_model="dwarf3"))
    session.simulation = False
    state = session.camera_state
    state.requested_frame_count = 2
    state.requested_bin = (2, 2)

    async def noop(*_args, **_kwargs):
        return None

    async def ensure_dark_library(*_args, **_kwargs):
        return True

    config_calls: dict[str, object] = {}

    async def fake_config(*, frames: int, binning: tuple[int, int]) -> None:
        config_calls["frames"] = frames
        config_calls["binning"] = binning

    async def fake_start(*, timeout: float, force_on_dark_warning: bool = False) -> int:
        config_calls["timeout"] = timeout
        config_calls["force_on_dark_warning"] = force_on_dark_warning
        return protocol_pb2.CODE_ASTRO_NEED_GOTO

    async def fake_fetch(fetch_state) -> None:
        fetch_state.last_end_time = time.time()

    monkeypatch.setattr(session, "_ensure_ws", noop)
    monkeypatch.setattr(session, "_enter_v3_astro_mode", noop)
    monkeypatch.setattr(session, "_ensure_exposure_settings", noop)
    monkeypatch.setattr(session, "_ensure_gain_settings", noop)
    monkeypatch.setattr(session, "_ensure_selected_filter", noop)
    monkeypatch.setattr(session, "_astro_go_live", noop)
    monkeypatch.setattr(session, "_ensure_dark_library", ensure_dark_library)
    monkeypatch.setattr(session, "_configure_astro_capture", fake_config)
    monkeypatch.setattr(session, "_refresh_capture_baseline", noop)
    monkeypatch.setattr(session, "_start_astro_capture", fake_start)
    monkeypatch.setattr(session, "_fetch_capture", fake_fetch)
    monkeypatch.setattr(session, "_has_recent_goto", lambda: False)

    await session.camera_start_exposure(0.5, True)

    assert state.capture_mode == "astro"
    assert state.last_error is None
    assert config_calls["frames"] == 2
    assert config_calls["binning"] == (2, 2)
    assert state.capture_task is not None
    await asyncio.wait_for(state.capture_task, timeout=0.5)
    state.capture_task = None


@pytest.mark.asyncio
async def test_camera_start_exposure_mini_rejects_unverified_photo_capture(monkeypatch):
    session = DwarfSession(
        Settings(
            force_simulation=True,
            dwarf_device_model="dwarfmini",
            dwarf_mini_capture_mode="photo",
        )
    )
    session.simulation = False
    state = session.camera_state
    state.requested_frame_count = 2
    state.requested_bin = (2, 2)

    calls: dict[str, object] = {}

    async def noop(*_args, **_kwargs):
        return None

    async def fake_photo_start(*, timeout: float) -> bool:
        calls["timeout"] = timeout
        return True

    async def fake_fetch(fetch_state) -> None:
        fetch_state.last_end_time = time.time()

    monkeypatch.setattr(session, "_ensure_ws", noop)
    monkeypatch.setattr(session, "_enter_v3_astro_mode", noop)
    monkeypatch.setattr(session, "_ensure_exposure_settings", noop)
    monkeypatch.setattr(session, "_ensure_gain_settings", noop)
    monkeypatch.setattr(session, "_ensure_selected_filter", noop)
    monkeypatch.setattr(session, "_refresh_capture_baseline", noop)
    monkeypatch.setattr(session, "_start_photo_capture", fake_photo_start)
    monkeypatch.setattr(session, "_fetch_capture", fake_fetch)

    with pytest.raises(CaptureConfigurationError, match="experimental"):
        await session.camera_start_exposure(0.5, True)

    assert state.capture_mode == "photo"
    assert calls == {}


@pytest.mark.asyncio
async def test_camera_start_exposure_mini_rejects_unverified_dark_workflow():
    session = DwarfSession(Settings(force_simulation=True, dwarf_device_model="dwarfmini"))
    session.simulation = False

    with pytest.raises(CaptureConfigurationError, match="dedicated calibration workflow"):
        await session.camera_start_exposure(1.0, False)

    assert session.camera_state.capture_phase == CapturePhase.FAILED
    assert session.camera_state.last_error == "mini_dark_calibration_unverified"


@pytest.mark.asyncio
async def test_start_photo_capture_uses_mini_fallback_on_timeout(monkeypatch):
    session = DwarfSession(Settings(force_simulation=True, dwarf_device_model="dwarfmini"))
    session.simulation = False

    calls: list[int] = []

    async def fake_send_and_check(module_id, command_id, request, **_kwargs):
        calls.append(command_id)
        if command_id == protocol_pb2.DwarfCMD.CMD_CAMERA_TELE_PHOTO_RAW:
            raise asyncio.TimeoutError()
        return None

    monkeypatch.setattr(session, "_send_and_check", fake_send_and_check)

    await session._start_photo_capture(timeout=2.0)

    assert calls == [
        protocol_pb2.DwarfCMD.CMD_CAMERA_TELE_PHOTO_RAW,
        protocol_pb2.DwarfCMD.CMD_CAMERA_TELE_PHOTOGRAPH,
    ]


@pytest.mark.asyncio
async def test_start_photo_capture_raises_timeout_for_non_mini(monkeypatch):
    session = DwarfSession(Settings(force_simulation=True, dwarf_device_model="dwarf3"))
    session.simulation = False

    async def fake_send_and_check(*_args, **_kwargs):
        raise asyncio.TimeoutError()

    monkeypatch.setattr(session, "_send_and_check", fake_send_and_check)

    with pytest.raises(asyncio.TimeoutError):
        await session._start_photo_capture(timeout=2.0)


@pytest.mark.asyncio
async def test_start_photo_capture_returns_false_when_mini_fallback_fails(monkeypatch):
    session = DwarfSession(Settings(force_simulation=True, dwarf_device_model="dwarfmini"))
    session.simulation = False

    async def fake_send_and_check(module_id, command_id, request, **_kwargs):
        if command_id == protocol_pb2.DwarfCMD.CMD_CAMERA_TELE_PHOTO_RAW:
            raise asyncio.TimeoutError()
        raise DwarfCommandError(module_id, command_id, -1)

    monkeypatch.setattr(session, "_send_and_check", fake_send_and_check)

    started = await session._start_photo_capture(timeout=2.0)
    assert started is False


@pytest.mark.asyncio
async def test_camera_go_live_after_capture(monkeypatch):
    session = DwarfSession(Settings(force_simulation=True))
    session.simulation = False
    session.settings.go_live_before_exposure = False
    state = session.camera_state
    state.requested_frame_count = 1
    state.requested_bin = (1, 1)

    async def fake_start(*, timeout: float, force_on_dark_warning: bool = False) -> int:
        return protocol_pb2.OK

    async def fake_stop(*_args, **_kwargs) -> None:
        return None

    async def fake_attempt_ftp(fetch_state) -> bool:
        fetch_state.image = object()
        fetch_state.last_end_time = time.time()
        return True

    async def ensure_dark(*_args, **_kwargs) -> bool:
        return True

    async def noop(*_args, **_kwargs):
        return None

    go_live_calls: list[bool] = []

    async def fake_go_live() -> None:
        go_live_calls.append(True)

    monkeypatch.setattr(session, "_ensure_ws", noop)
    monkeypatch.setattr(session, "_enter_v3_astro_mode", noop)
    monkeypatch.setattr(session, "_ensure_exposure_settings", noop)
    monkeypatch.setattr(session, "_ensure_gain_settings", noop)
    monkeypatch.setattr(session, "_ensure_selected_filter", noop)
    monkeypatch.setattr(session, "_ensure_dark_library", ensure_dark)
    monkeypatch.setattr(session, "_configure_astro_capture", noop)
    monkeypatch.setattr(session, "_refresh_capture_baseline", noop)
    monkeypatch.setattr(session, "_start_astro_capture", fake_start)
    monkeypatch.setattr(session, "_stop_astro_capture", fake_stop)
    monkeypatch.setattr(session, "_attempt_ftp_capture", fake_attempt_ftp)
    monkeypatch.setattr(session, "_astro_go_live", fake_go_live)
    monkeypatch.setattr(session, "_has_recent_goto", lambda: True)

    await session.camera_start_exposure(0.2, True)

    assert state.capture_task is not None
    await asyncio.wait_for(state.capture_task, timeout=0.5)
    state.capture_task = None

    assert go_live_calls == [True]
    assert state.image is not None


@pytest.mark.asyncio
async def test_start_astro_capture_dispatches_without_waiting_for_v3_response(monkeypatch):
    session = DwarfSession(
        Settings(
            force_simulation=True,
            dwarf_device_model="dwarfmini",
            capture_start_evidence_timeout_seconds=0.01,
        )
    )
    session.simulation = False

    response_future = asyncio.get_running_loop().create_future()

    async def fake_begin_request(*_args, **_kwargs):
        return response_future

    monkeypatch.setattr(session, "_begin_request", fake_begin_request)

    assert await session._start_astro_capture(timeout=5.0) == protocol_pb2.OK
    task = session._capture_start_response_task
    assert task is not None
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_start_astro_capture_timeout_with_progress_evidence_succeeds(monkeypatch):
    session = DwarfSession(
        Settings(
            force_simulation=True,
            dwarf_device_model="dwarfmini",
            capture_start_evidence_timeout_seconds=0.01,
        )
    )
    session.simulation = False

    async def fake_begin_request(*_args, **_kwargs):
        session._v3_exposure_progress = (1, 30)
        session._capture_start_evidence_event.set()
        future = asyncio.get_running_loop().create_future()
        response = ComResponse()
        response.code = protocol_pb2.OK
        future.set_result(response)
        return future

    monkeypatch.setattr(session, "_begin_request", fake_begin_request)

    assert await session._start_astro_capture(timeout=5.0) == protocol_pb2.OK


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "dark_warning_code",
    [
        protocol_pb2.CODE_ASTRO_DARK_NOT_FOUND,
        protocol_pb2.CODE_ASTRO_DARK_TEMP_MISMATCH,
    ],
)
async def test_start_astro_capture_uses_continue_command_for_dark_warning(
    monkeypatch, dark_warning_code
):
    session = DwarfSession(Settings(force_simulation=True, dwarf_device_model="dwarf3"))
    session.simulation = False
    await session._get_filter_options()
    session.camera_state.filter_index = 1
    requests: list[tuple[int, bytes]] = []

    async def fake_begin_request(_module, command, request, _response_cls):
        requests.append((command, request.SerializeToString()))
        response = ComResponse()
        response.code = (
            dark_warning_code
            if len(requests) == 1
            else protocol_pb2.CODE_ASTRO_NEED_GOTO
        )
        future = asyncio.get_running_loop().create_future()
        future.set_result(response)
        return future

    monkeypatch.setattr(session, "_begin_request", fake_begin_request)
    monkeypatch.setattr(session, "_has_recent_goto", lambda: True)

    code = await session._start_astro_capture(timeout=5.0, force_on_dark_warning=True)
    monitor = session._capture_start_response_task
    assert monitor is not None
    await asyncio.wait_for(monitor, timeout=0.5)

    assert code == protocol_pb2.OK
    assert [command for command, _ in requests] == [11005, 11050]
    start_request = astro_pb2.ReqCaptureRawLiveStacking.FromString(requests[0][1])
    assert start_request.ir_index == 1
    assert start_request.force_start is False
    assert requests[1][1] == b""


@pytest.mark.asyncio
async def test_delayed_dark_temperature_warning_retries_without_failing_capture(monkeypatch):
    session = DwarfSession(Settings(force_simulation=True, dwarf_device_model="dwarf3"))
    session.simulation = False
    await session._get_filter_options()
    session.camera_state.filter_index = 1
    session.camera_state.capture_id = "capture-under-test"
    requests: list[tuple[int, bytes]] = []
    futures: list[asyncio.Future[ComResponse]] = []

    async def fake_begin_request(_module, command, request, _response_cls):
        requests.append((command, request.SerializeToString()))
        future = asyncio.get_running_loop().create_future()
        futures.append(future)
        return future

    monkeypatch.setattr(session, "_begin_request", fake_begin_request)
    monkeypatch.setattr(session, "_has_recent_goto", lambda: True)

    assert (
        await session._start_astro_capture(
            timeout=5.0,
            force_on_dark_warning=True,
        )
        == protocol_pb2.OK
    )
    monitor = session._capture_start_response_task
    assert monitor is not None

    mismatch = ComResponse()
    mismatch.code = protocol_pb2.CODE_ASTRO_DARK_TEMP_MISMATCH
    futures[0].set_result(mismatch)
    for _ in range(10):
        if len(futures) == 2:
            break
        await asyncio.sleep(0)

    assert len(futures) == 2
    assert [command for command, _ in requests] == [11005, 11050]
    assert requests[1][1] == b""
    accepted_warning = ComResponse()
    accepted_warning.code = protocol_pb2.CODE_ASTRO_NEED_GOTO
    futures[1].set_result(accepted_warning)
    await asyncio.wait_for(monitor, timeout=0.5)

    assert session.camera_state.capture_id == "capture-under-test"
    assert session.camera_state.capture_phase is not CapturePhase.FAILED


@pytest.mark.asyncio
async def test_dwarf2_dark_warning_uses_force_start_fallback(monkeypatch):
    session = DwarfSession(Settings(force_simulation=True, dwarf_device_model="dwarf2"))
    session.simulation = False
    requests: list[tuple[int, astro_pb2.ReqCaptureRawLiveStacking]] = []

    async def fake_begin_request(_module, command, request, _response_cls):
        decoded = astro_pb2.ReqCaptureRawLiveStacking.FromString(
            request.SerializeToString()
        )
        requests.append((command, decoded))
        response = ComResponse()
        response.code = (
            protocol_pb2.CODE_ASTRO_DARK_NOT_FOUND
            if len(requests) == 1
            else protocol_pb2.OK
        )
        future = asyncio.get_running_loop().create_future()
        future.set_result(response)
        return future

    monkeypatch.setattr(session, "_begin_request", fake_begin_request)

    assert (
        await session._start_astro_capture(
            timeout=5.0,
            force_on_dark_warning=True,
        )
        == protocol_pb2.OK
    )
    monitor = session._capture_start_response_task
    assert monitor is not None
    await asyncio.wait_for(monitor, timeout=0.5)

    assert [command for command, _ in requests] == [11005, 11005]
    assert [request.force_start for _, request in requests] == [False, True]
    assert [request.ir_index for _, request in requests] == [-1, -1]


@pytest.mark.asyncio
async def test_stop_astro_capture_dispatches_without_waiting_for_v3_response(monkeypatch):
    session = DwarfSession(Settings(force_simulation=True, dwarf_device_model="dwarf3"))
    session.simulation = False
    response_future = asyncio.get_running_loop().create_future()
    commands: list[int] = []

    async def fake_begin_request(_module, command, _request, _response_cls):
        commands.append(command)
        return response_future

    monkeypatch.setattr(session, "_begin_request", fake_begin_request)

    await asyncio.wait_for(session._stop_astro_capture(strict=True), timeout=0.1)

    assert commands == [protocol_pb2.DwarfCMD.CMD_ASTRO_STOP_CAPTURE_RAW_LIVE_STACKING]
    task = session._capture_stop_response_task
    assert task is not None
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


def test_decode_v3_device_config_payload_extracts_known_fields():
    raw = bytes.fromhex(
        "0a040a020803120208011900000060b81e014021000000403333f33f28800f30b808"
    )
    parsed = _decode_v3_device_config_payload(raw)

    assert parsed.get("capture_raw_state") == 3
    assert parsed.get("field2_mode") == 1
    assert parsed.get("image_width") == 1920
    assert parsed.get("image_height") == 1080
    assert parsed.get("field3_double") == pytest.approx(2.140000104904175)
    assert parsed.get("field4_double") == pytest.approx(1.2000000476837158)
    legacy = parsed.get("legacy_camera")
    assert isinstance(legacy, dict)
    assert legacy.get("id") == 0
    assert legacy.get("name") == "Tele"
    assert legacy.get("previewWidth") == 1920
    assert legacy.get("previewHeight") == 1080
    assert legacy.get("fvWidth") == pytest.approx(2.140000104904175)
    assert legacy.get("fvHeight") == pytest.approx(1.2000000476837158)


def test_capture_state_notification_controls_device_ready_event():
    session = DwarfSession(Settings(force_simulation=True, dwarf_device_model="dwarfmini"))

    session._handle_astro_capture_state_notification(types.SimpleNamespace(data=b"\x08\x01"))
    assert session._astro_capture_operation_state == 1
    assert not session._astro_capture_ready_event.is_set()

    session._handle_astro_capture_state_notification(types.SimpleNamespace(data=b"\x08\x02"))
    assert session._astro_capture_operation_state == 2
    assert not session._astro_capture_ready_event.is_set()

    session._handle_astro_capture_state_notification(types.SimpleNamespace(data=b"\x08\x03"))
    assert session._astro_capture_operation_state == 3
    assert session._astro_capture_ready_event.is_set()

    session._handle_astro_capture_state_notification(types.SimpleNamespace(data=b""))
    assert session._astro_capture_operation_state == 0
    assert session._astro_capture_ready_event.is_set()


@pytest.mark.asyncio
async def test_next_capture_waits_until_firmware_reports_stopped():
    session = DwarfSession(Settings(force_simulation=True, dwarf_device_model="dwarfmini"))
    session._set_astro_capture_operation_state(2, source="test")

    wait_task = asyncio.create_task(session._wait_for_astro_capture_ready(timeout=0.5))
    await asyncio.sleep(0)
    assert not wait_task.done()

    session._set_astro_capture_operation_state(3, source="test")
    await asyncio.wait_for(wait_task, timeout=0.1)


@pytest.mark.asyncio
@pytest.mark.parametrize("model", ["dwarf2", "dwarf3", "dwarfmini"])
async def test_camera_connect_uses_enter_camera_and_preview_quality_for_all_models(
    monkeypatch, model
):
    session = DwarfSession(Settings(force_simulation=True, dwarf_device_model=model))
    session.simulation = False

    captured: list[tuple[int, int, object]] = []

    async def fake_ensure_ws(*_args, **_kwargs):
        return None

    async def fake_send_request(module_id, command_id, request, _response_cls, **_kwargs):
        captured.append((module_id, command_id, request))
        return ResEnterCamera(code=protocol_pb2.OK, shooting_mode_id=8)

    async def fake_send_and_check(module_id, command_id, request, **_kwargs):
        captured.append((module_id, command_id, request))
        return None

    monkeypatch.setattr(session, "_ensure_ws", fake_ensure_ws)
    monkeypatch.setattr(session, "_send_request", fake_send_request)
    monkeypatch.setattr(session, "_send_and_check", fake_send_and_check)

    await session.camera_connect()

    assert [command for _, command, _ in captured] == [16404, 10050]
    assert captured[0][2].client_param.encode_type == 1
    assert captured[1][2].level == 1
    assert session.camera_state.connected is True


@pytest.mark.asyncio
async def test_camera_connect_failure_does_not_claim_connected(monkeypatch):
    session = DwarfSession(Settings(force_simulation=True, dwarf_device_model="dwarfmini"))
    session.simulation = False

    async def fake_ensure_ws(*_args, **_kwargs):
        return None

    async def fake_send_request(*_args, **_kwargs):
        raise RuntimeError("camera open rejected")

    monkeypatch.setattr(session, "_ensure_ws", fake_ensure_ws)
    monkeypatch.setattr(session, "_send_request", fake_send_request)

    with pytest.raises(RuntimeError, match="camera open rejected"):
        await session.camera_connect()

    assert session.camera_state.connected is False


@pytest.mark.asyncio
async def test_v3_camera_disconnect_is_local_only(monkeypatch):
    session = DwarfSession(Settings(dwarf_device_model="dwarfmini"))
    session.simulation = False
    session.camera_state.capture_task = None
    session.camera_state.connected = True

    async def fake_ensure_ws(self):
        raise AssertionError("V3 camera disconnect must not reopen the WebSocket")

    session._ensure_ws = types.MethodType(fake_ensure_ws, session)

    await session.camera_disconnect()

    assert session.camera_state.connected is False


@pytest.mark.asyncio
async def test_gain_commands_disable_after_timeout(monkeypatch):
    session = DwarfSession(Settings(force_simulation=True))
    session.simulation = False
    session.camera_state.requested_gain = 42
    monkeypatch.setattr(session, "_uses_v3_protocol", lambda: False)

    calls = {"mode": 0, "index": 0}

    async def failing_mode(*, timeout):
        calls["mode"] += 1
        raise asyncio.TimeoutError()

    async def failing_index(*args, **kwargs):  # pragma: no cover - unreachable in this test
        calls["index"] += 1
        raise asyncio.TimeoutError()

    async def resolve_gain(value: int) -> tuple[int, int]:
        return value, value

    async def manual_supported() -> bool:
        return True

    monkeypatch.setattr(session, "_set_gain_mode_manual", failing_mode)
    monkeypatch.setattr(session, "_set_gain_index", failing_index)
    monkeypatch.setattr(session, "_resolve_gain_command", resolve_gain)
    monkeypatch.setattr(session, "_gain_manual_mode_enabled", manual_supported)

    with pytest.raises(CaptureConfigurationError, match="manual gain"):
        await session._ensure_gain_settings()

    assert session._gain_command_supported is False
    assert session.camera_state.applied_gain_index is None
    assert calls == {"mode": 1, "index": 0}

    calls["mode"] = 0

    with pytest.raises(CaptureConfigurationError, match="unavailable"):
        await session._ensure_gain_settings()

    assert calls == {"mode": 0, "index": 0}


@pytest.mark.asyncio
async def test_gain_commands_applied_successfully(monkeypatch):
    session = DwarfSession(Settings(force_simulation=True))
    session.simulation = False
    session.camera_state.requested_gain = 17
    monkeypatch.setattr(session, "_uses_v3_protocol", lambda: False)

    calls = {"mode": 0, "index": 0}

    async def successful_mode(*, timeout):
        calls["mode"] += 1

    async def successful_index(index: int, *, timeout=None):
        calls["index"] += 1
        assert index == 5
        assert timeout is not None

    async def resolve_gain(value: int) -> tuple[int, int]:
        return 17, 5

    async def manual_supported() -> bool:
        return True

    monkeypatch.setattr(session, "_set_gain_mode_manual", successful_mode)
    monkeypatch.setattr(session, "_set_gain_index", successful_index)
    monkeypatch.setattr(session, "_resolve_gain_command", resolve_gain)
    monkeypatch.setattr(session, "_gain_manual_mode_enabled", manual_supported)

    await session._ensure_gain_settings()

    assert session._gain_command_supported is True
    assert session.camera_state.applied_gain_index == 17
    assert calls == {"mode": 1, "index": 1}

    await session._ensure_gain_settings()

    assert calls == {"mode": 1, "index": 1}


@pytest.mark.asyncio
async def test_session_shutdown_unlocks_master_lock():
    session = DwarfSession(Settings(force_simulation=False))
    session.simulation = False
    session._master_lock_acquired = True
    session._refs = {"camera": 1, "telescope": 1, "focuser": 1, "filterwheel": 1}

    capture_task = asyncio.create_task(asyncio.sleep(10))
    session.camera_state.capture_task = capture_task

    class DummyWsClient:
        def __init__(self) -> None:
            self.connected = False
            self.connect_calls = 0
            self.send_requests = []
            self.close_called = False

        async def connect(self) -> None:
            self.connected = True
            self.connect_calls += 1

        async def send_request(
            self,
            module_id,
            command,
            message,
            response_type,
            *,
            timeout: float,
            expected_responses,
        ):
            self.send_requests.append(message)
            response = response_type()
            if isinstance(response, ComResponse):
                response.code = protocol_pb2.OK
            return response

        async def close(self) -> None:
            self.close_called = True
            self.connected = False

        def register_notification_handler(self, *_args, **_kwargs) -> None:
            pass

    class DummyHttpClient:
        def __init__(self) -> None:
            self.closed = False

        async def aclose(self) -> None:
            self.closed = True

    session._ws_client = DummyWsClient()  # type: ignore[assignment]
    session._http_client = DummyHttpClient()  # type: ignore[assignment]

    await session.shutdown()

    assert capture_task.cancelled()
    assert session._ws_client.close_called  # type: ignore[attr-defined]
    assert session._http_client.closed  # type: ignore[attr-defined]
    assert session._ws_client.connect_calls == 1  # type: ignore[attr-defined]
    assert session._master_lock_acquired is False
    assert all(count == 0 for count in session._refs.values())
    assert session._ws_bootstrapped is False
    assert len(session._ws_client.send_requests) == 1  # type: ignore[attr-defined]
    assert session._ws_client.send_requests[0].lock is False  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_resolve_gain_command_uses_params_config():
    session = DwarfSession(Settings(force_simulation=True))
    session.simulation = False
    session._params_config = {
        "data": {
            "cameras": [
                {
                    "name": "Tele",
                    "supportParams": [
                        {
                            "name": "Gain",
                            "hasAuto": False,
                            "gearMode": {
                                "values": [
                                    {"index": 0, "name": "0"},
                                    {"index": 24, "name": "80"},
                                    {"index": 27, "name": "90"},
                                ]
                            },
                            "supportMode": [{"index": 0, "name": "Gear Mode"}],
                        }
                    ],
                }
            ]
        }
    }

    applied_gain, command_index = await session._resolve_gain_command(80)
    assert applied_gain == 80
    assert command_index == 24

    snapped_gain, snapped_index = await session._resolve_gain_command(83)
    assert snapped_gain == 80
    assert snapped_index == 24

    manual_supported = await session._gain_manual_mode_enabled()
    assert manual_supported is False
