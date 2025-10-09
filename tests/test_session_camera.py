import asyncio
import time

import pytest

from dwarf_alpaca.config.settings import Settings
from dwarf_alpaca.dwarf.session import DwarfSession
from dwarf_alpaca.proto import protocol_pb2
from dwarf_alpaca.proto.dwarf_messages import (
    ComResponse,
    ResNotifyTemperature,
    WsPacket,
    TYPE_NOTIFICATION,
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


@pytest.mark.asyncio
async def test_camera_start_exposure_simulation_sets_astro_mode():
    session = DwarfSession(Settings(force_simulation=True))
    state = session.camera_state
    state.requested_frame_count = 3
    state.requested_bin = (2, 2)

    await session.camera_start_exposure(0.1, True)

    assert state.capture_mode == "astro"
    assert state.requested_frame_count == 3
    assert state.requested_bin == (2, 2)
    assert state.image is not None


@pytest.mark.asyncio
async def test_camera_start_exposure_requires_goto(monkeypatch):
    session = DwarfSession(Settings(force_simulation=True))
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

    async def fake_start(*, timeout: float) -> int:
        config_calls["timeout"] = timeout
        return protocol_pb2.CODE_ASTRO_NEED_GOTO

    async def fake_fetch(fetch_state) -> None:
        fetch_state.last_end_time = time.time()

    monkeypatch.setattr(session, "_ensure_ws", noop)
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
async def test_camera_go_live_after_capture(monkeypatch):
    session = DwarfSession(Settings(force_simulation=True))
    session.simulation = False
    session.settings.go_live_before_exposure = False
    state = session.camera_state
    state.requested_frame_count = 1
    state.requested_bin = (1, 1)

    async def fake_start(*, timeout: float) -> int:
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
