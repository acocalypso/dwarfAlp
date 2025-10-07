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
