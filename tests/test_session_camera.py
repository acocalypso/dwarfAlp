import pytest

from dwarf_alpaca.config.settings import Settings
from dwarf_alpaca.dwarf.session import DwarfSession
from dwarf_alpaca.proto import protocol_pb2
from dwarf_alpaca.proto.dwarf_messages import ResNotifyTemperature, WsPacket, TYPE_NOTIFICATION


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
