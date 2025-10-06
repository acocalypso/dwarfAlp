from __future__ import annotations

import asyncio
import json
import socket
from dataclasses import dataclass
from typing import Any

import structlog

from .config.settings import Settings

DEVICE_LIST = [
    {
        "DeviceName": "DWARF 3 Telescope",
        "DeviceType": "Telescope",
        "DeviceNumber": 0,
        "UniqueID": "DWARF3-Telescope",
    },
    {
        "DeviceName": "DWARF 3 Camera",
        "DeviceType": "Camera",
        "DeviceNumber": 0,
        "UniqueID": "DWARF3-Camera",
    },
    {
        "DeviceName": "DWARF 3 Focuser",
        "DeviceType": "Focuser",
        "DeviceNumber": 0,
        "UniqueID": "DWARF3-Focuser",
    },
    {
        "DeviceName": "DWARF 3 Filter Wheel",
        "DeviceType": "FilterWheel",
        "DeviceNumber": 0,
        "UniqueID": "DWARF3-FilterWheel",
    },
]

logger = structlog.get_logger(__name__)


@dataclass
class DiscoveryService:
    """Implements the Alpaca UDP discovery responder."""

    settings: Settings
    _task: asyncio.Task[None] | None = None

    async def __aenter__(self) -> "DiscoveryService":
        self._task = asyncio.create_task(self._serve())
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _serve(self) -> None:
        loop = asyncio.get_running_loop()
        transport, protocol = await loop.create_datagram_endpoint(
            lambda: _DiscoveryProtocol(self.settings),
            local_addr=(self.settings.discovery_interface, self.settings.discovery_port),
            allow_broadcast=True,
        )
        logger.info(
            "discovery.started",
            interface=self.settings.discovery_interface,
            port=self.settings.discovery_port,
        )
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            logger.info("discovery.stopping")
        finally:
            transport.close()


class _DiscoveryProtocol(asyncio.DatagramProtocol):
    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self.settings = settings
        self.transport: asyncio.transports.DatagramTransport | None = None
        self._advertised_host = _resolve_advertised_host(settings)
        logger.info(
            "discovery.advertising",
            advertised_host=self._advertised_host,
            port=self.settings.http_port,
        )

    def datagram_received(self, data: bytes, addr):
        message = data.decode(errors="ignore").strip()
        if "alpaca" not in message.lower():
            return

        response = build_discovery_payload(self.settings, self._advertised_host)
        payload = json.dumps(response).encode()

        if self.transport is None:
            return
        self.transport.sendto(payload, addr)
        logger.debug("discovery.responded", address=addr)

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport  # type: ignore[assignment]

    def error_received(self, exc: Exception) -> None:
        logger.warning("discovery.error", error=str(exc))


def _resolve_advertised_host(settings: Settings) -> str:
    host = settings.http_advertise_host or settings.http_host
    if host in {"0.0.0.0", "::", "127.0.0.1", "::1"}:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.connect(("8.8.8.8", 80))
                resolved = sock.getsockname()[0]
                if resolved and not resolved.startswith("127."):
                    host = resolved
        except OSError:
            try:
                resolved = socket.gethostbyname(socket.gethostname())
                if resolved and not resolved.startswith("127."):
                    host = resolved
            except OSError:
                pass
    return host


def build_discovery_payload(settings: Settings, advertised_host: str) -> dict[str, Any]:
    return {
        "AlpacaVersion": 1,
        "AlpacaPort": settings.http_port,
        "ServerName": "DWARF 3 Alpaca Server",
        "Manufacturer": "Astro Tools",
        "ManufacturerVersion": "0.1.0",
        "Location": "Observatory",
        "ServerID": "DWARF3-0001",
        "ServerUrl": f"{settings.http_scheme}://{advertised_host}:{settings.http_port}",
        "DeviceCount": len(DEVICE_LIST),
        "Devices": DEVICE_LIST,
        "DeviceList": DEVICE_LIST,
    }
