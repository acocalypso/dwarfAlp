from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple, Type, TypeVar

import websockets
from google.protobuf.message import Message
from websockets.exceptions import ConnectionClosedOK

from ..proto.dwarf_messages import (
    ComResponse,
    TYPE_NOTIFICATION,
    TYPE_NOTIFICATION_RESPONSE,
    TYPE_REQUEST,
    TYPE_REQUEST_RESPONSE,
    WsPacket,
)

ResponseT = TypeVar("ResponseT", bound=Message)
NotificationHandler = Callable[[WsPacket], Awaitable[None]]


@dataclass
class _PendingRequest:
    future: asyncio.Future[Message]
    response_cls: Type[Message]
    alternate_responses: Dict[Tuple[int, int], Type[Message]] = field(default_factory=dict)


class DwarfWsClient:
    """Lightweight websocket client for DWARF control plane."""

    def __init__(
        self,
        host: str,
        *,
        port: int = 9900,
        major_version: int = 1,
        minor_version: int = 2,
        device_id: int = 1,
        client_id: str | None = None,
    ) -> None:
        self.uri = f"ws://{host}:{port}/"
        self.major_version = major_version
        self.minor_version = minor_version
        self.device_id = device_id
        self._client_id = client_id or ""

        self._lock = asyncio.Lock()
        self._conn: Optional[websockets.WebSocketClientProtocol] = None
        self._reader_task: Optional[asyncio.Task[None]] = None
        self._pending: Dict[Tuple[int, int], _PendingRequest] = {}
        self._pending_aliases: Dict[Tuple[int, int], Tuple[int, int]] = {}
        self._notifications: set[NotificationHandler] = set()
        self._connected_event = asyncio.Event()

    def set_client_id(self, client_id: str | None) -> None:
        self._client_id = client_id or ""

    def _pop_pending_request(self, key: Tuple[int, int]) -> Optional[_PendingRequest]:
        pending = self._pending.pop(key, None)
        if pending:
            for alias_key in pending.alternate_responses:
                if self._pending_aliases.get(alias_key) == key:
                    self._pending_aliases.pop(alias_key, None)
        return pending

    @property
    def connected(self) -> bool:
        conn = self._conn
        if conn is None:
            return False

        closed_attr = getattr(conn, "closed", None)
        if closed_attr is None:
            close_code = getattr(conn, "close_code", None)
            return close_code is None

        if callable(closed_attr):
            try:
                closed_value = closed_attr()
            except TypeError:
                closed_value = False
        else:
            closed_value = closed_attr

        return not bool(closed_value)

    async def connect(self) -> None:
        if self.connected:
            return
        async with self._lock:
            if self.connected:
                return
            self._conn = await websockets.connect(self.uri, ping_interval=None)
            self._connected_event.set()
            self._reader_task = asyncio.create_task(self._reader_loop())

    async def close(self) -> None:
        async with self._lock:
            if self._reader_task:
                self._reader_task.cancel()
                with contextlib.suppress(Exception):
                    await self._reader_task
                self._reader_task = None
            if self._conn:
                with contextlib.suppress(Exception):
                    await self._conn.close()
                self._conn = None
            self._connected_event.clear()
            self._flush_pending(ConnectionClosedOK(None, None))

    async def wait_connected(self) -> None:
        await self._connected_event.wait()

    async def send_request(
        self,
        module_id: int,
        command_id: int,
        request_message: Message,
        response_cls: Type[ResponseT],
        *,
        timeout: float = 10.0,
        expected_responses: Optional[Dict[Tuple[int, int], Type[Message]]] = None,
    ) -> Message:
        await self.connect()
        if not self._conn:
            raise RuntimeError("DWARF websocket connection unavailable")

        key = (module_id, command_id)
        loop = asyncio.get_running_loop()
        if key in self._pending:
            raise RuntimeError(
                f"Another request for module {module_id} cmd {command_id} is already pending"
            )
        future: asyncio.Future[Message] = loop.create_future()
        alternates = dict(expected_responses or {})
        self._pending[key] = _PendingRequest(future=future, response_cls=response_cls, alternate_responses=alternates)
        for alias_key in alternates:
            self._pending_aliases[alias_key] = key

        packet = WsPacket()
        packet.major_version = self.major_version
        packet.minor_version = self.minor_version
        packet.device_id = self.device_id
        packet.module_id = module_id
        packet.cmd = command_id
        packet.type = TYPE_REQUEST
        packet.data = request_message.SerializeToString()
        if self._client_id:
            packet.client_id = self._client_id

        try:
            await self._conn.send(packet.SerializeToString())
            message = await asyncio.wait_for(future, timeout=timeout)
        except Exception:
            self._pop_pending_request(key)
            raise
        return message

    async def send_command(
        self,
        module_id: int,
        command_id: int,
        request_message: Message,
        *,
        timeout: float = 10.0,
        expected_responses: Optional[Dict[Tuple[int, int], Type[Message]]] = None,
    ) -> Message:
        response = await self.send_request(
            module_id,
            command_id,
            request_message,
            ComResponse,
            timeout=timeout,
            expected_responses=expected_responses,
        )
        return response

    def register_notification_handler(self, handler: NotificationHandler) -> None:
        self._notifications.add(handler)

    def unregister_notification_handler(self, handler: NotificationHandler) -> None:
        self._notifications.discard(handler)

    async def _reader_loop(self) -> None:
        assert self._conn is not None
        try:
            async for payload in self._conn:
                if isinstance(payload, str):
                    payload = payload.encode()
                packet = WsPacket()
                packet.ParseFromString(payload)
                await self._dispatch_packet(packet)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            self._flush_pending(exc)
        finally:
            self._connected_event.clear()
            self._conn = None

    async def _dispatch_packet(self, packet: Message) -> None:
        packet_type = getattr(packet, "type", None)
        module_id = getattr(packet, "module_id", 0)
        command_id = getattr(packet, "cmd", 0)
        key = (module_id, command_id)

        pending = self._pop_pending_request(key)
        response_cls: Optional[Type[Message]] = None
        if pending is None:
            original_key = self._pending_aliases.pop(key, None)
            if original_key is not None:
                pending = self._pop_pending_request(original_key)
                if pending:
                    response_cls = pending.alternate_responses.get(key, pending.response_cls)
        else:
            response_cls = pending.response_cls

        if pending and not pending.future.done():
            try:
                if response_cls is None:
                    result: Message = packet
                else:
                    result = response_cls()
                    raw_data = getattr(packet, "data", b"")
                    result.ParseFromString(raw_data)
                pending.future.set_result(result)
            except Exception as exc:  # pragma: no cover - defensive
                pending.future.set_exception(exc)

        if packet_type == TYPE_NOTIFICATION:
            await asyncio.gather(
                *(handler(packet) for handler in list(self._notifications)),
                return_exceptions=True,
            )

    def _flush_pending(self, error: Exception) -> None:
        for pending in self._pending.values():
            if not pending.future.done():
                pending.future.set_exception(error)
        self._pending.clear()
        self._pending_aliases.clear()


class DwarfCommandError(RuntimeError):
    """Raised when DWARF returns a non-zero error code."""

    def __init__(self, module_id: int, command_id: int, code: int) -> None:
        super().__init__(f"DWARF command {module_id}:{command_id} failed with code {code}")
        self.module_id = module_id
        self.command_id = command_id
        self.code = code


async def send_and_check(
    client: DwarfWsClient,
    module_id: int,
    command_id: int,
    request: Message,
    *,
    timeout: float = 10.0,
) -> None:
    response = await client.send_command(module_id, command_id, request, timeout=timeout)
    if response.code != 0:
        raise DwarfCommandError(module_id, command_id, response.code)


__all__ = [
    "DwarfWsClient",
    "DwarfCommandError",
    "send_and_check",
]
