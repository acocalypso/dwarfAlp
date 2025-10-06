from __future__ import annotations

import asyncio

import pytest

from dwarf_alpaca.dwarf.ws_client import DwarfWsClient
from dwarf_alpaca.proto.dwarf_messages import (
    ComResponse,
    ReqCloseCamera,
    ReqsetMasterLock,
    ResNotifyHostSlaveMode,
    TYPE_NOTIFICATION,
    TYPE_REQUEST_RESPONSE,
    WsPacket,
)
from dwarf_alpaca.proto import protocol_pb2


def test_ws_client_connected_handles_missing_closed():
    client = DwarfWsClient("127.0.0.1")

    class MinimalConn:
        def __init__(self) -> None:
            self.close_code = None

        async def close(self) -> None:
            pass

    dummy_conn = MinimalConn()
    client._conn = dummy_conn  # type: ignore[attr-defined]
    assert client.connected is True

    dummy_conn.close_code = 1000
    assert client.connected is False


class DummyConnection:
    def __init__(
        self,
        client: DwarfWsClient,
        response_builder=None,
    ) -> None:
        self.client = client
        self.sent_packets = []
        self.close_code = None
        self.closed = False
        self._response_builder = response_builder or self._default_response_builder

    async def send(self, data: bytes) -> None:
        packet = WsPacket()
        packet.ParseFromString(data)
        self.sent_packets.append(packet)
        responses = self._response_builder(packet)
        for response_packet in responses:
            asyncio.create_task(self.client._dispatch_packet(response_packet))

    async def close(self) -> None:
        self.closed = True

    def _default_response_builder(self, packet):
        response_packet = WsPacket()
        response_packet.module_id = packet.module_id
        response_packet.cmd = packet.cmd
        response_packet.type = TYPE_REQUEST_RESPONSE
        response = ComResponse()
        response.code = 0
        response_packet.data = response.SerializeToString()
        return [response_packet]


@pytest.mark.asyncio
async def test_ws_client_includes_client_id():
    client = DwarfWsClient("127.0.0.1", client_id="alpaca-test")
    dummy = DummyConnection(client)
    client._conn = dummy  # type: ignore[attr-defined]
    client._connected_event.set()

    request = ReqCloseCamera()
    response = await client.send_command(1, 42, request)

    assert response.code == 0
    assert dummy.sent_packets
    assert dummy.sent_packets[0].client_id == "alpaca-test"


@pytest.mark.asyncio
async def test_ws_client_handles_master_lock_notification():
    client = DwarfWsClient("127.0.0.1")

    def response_builder(packet):
        notification = WsPacket()
        notification.module_id = protocol_pb2.ModuleId.MODULE_SYSTEM
        notification.cmd = protocol_pb2.DwarfCMD.CMD_NOTIFY_WS_HOST_SLAVE_MODE
        notification.type = TYPE_NOTIFICATION
        payload = ResNotifyHostSlaveMode()
        payload.mode = 0
        payload.lock = True
        notification.data = payload.SerializeToString()
        return [notification]

    dummy = DummyConnection(client, response_builder=response_builder)
    client._conn = dummy  # type: ignore[attr-defined]
    client._connected_event.set()

    request = ReqsetMasterLock()
    request.lock = True
    expected = {
        (
            protocol_pb2.ModuleId.MODULE_SYSTEM,
            protocol_pb2.DwarfCMD.CMD_NOTIFY_WS_HOST_SLAVE_MODE,
        ): ResNotifyHostSlaveMode,
    }

    response = await client.send_request(
        protocol_pb2.ModuleId.MODULE_SYSTEM,
        protocol_pb2.DwarfCMD.CMD_SYSTEM_SET_MASTERLOCK,
        request,
        ComResponse,
        expected_responses=expected,
    )

    assert isinstance(response, ResNotifyHostSlaveMode)
    assert response.mode == 0
    assert response.lock is True
