import asyncio
import types

import pytest

from dwarf_alpaca.config.settings import Settings
from dwarf_alpaca.dwarf.session import DwarfSession
from dwarf_alpaca.proto import protocol_pb2
from dwarf_alpaca.proto.dwarf_messages import ResNotifyFocus, WsPacket, TYPE_NOTIFICATION


@pytest.mark.asyncio
async def test_focus_notification_updates_state():
    session = DwarfSession(Settings(force_simulation=True))

    message = ResNotifyFocus()
    message.focus = 4321
    packet = WsPacket()
    packet.module_id = protocol_pb2.ModuleId.MODULE_NOTIFY
    packet.cmd = protocol_pb2.DwarfCMD.CMD_NOTIFY_FOCUS
    packet.type = TYPE_NOTIFICATION
    packet.data = message.SerializeToString()

    assert session.focuser_state.position == 0
    await session._handle_notification(packet)

    assert session.focuser_state.position == 4321
    assert session.focuser_state.last_update is not None
    assert session._focus_update_event.is_set()


@pytest.mark.asyncio
async def test_focuser_move_fallback_without_notifications(monkeypatch):
    session = DwarfSession(Settings())
    session.focuser_state.position = 100

    async def _noop(self, *args, **kwargs):
        return None

    session._ensure_ws = types.MethodType(_noop, session)
    session._send_and_check = types.MethodType(_noop, session)

    async def _never_wait(self):
        await asyncio.sleep(1)

    session._focus_update_event.wait = types.MethodType(_never_wait, session._focus_update_event)

    await session.focuser_move(20, target=120)

    assert session.focuser_state.position == 120
    assert session.focuser_state.last_update is not None
    assert session.focuser_state.is_moving is False