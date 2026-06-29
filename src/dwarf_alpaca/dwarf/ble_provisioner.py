from __future__ import annotations

import asyncio
import contextlib
import sys
from dataclasses import dataclass
from typing import Any, Optional, TYPE_CHECKING, cast

import structlog

from ..proto import ble_pb2
from .ble_packets import (
    DEFAULT_BLE_PASSWORD,
    DWARF_CHARACTERISTIC_UUID,
    BlePacketError,
    ParsedPacket,
    build_req_getconfig,
    build_req_getwifilist,
    build_req_sta,
    describe_ble_error,
    parse_notification,
)

try:  # pragma: no cover - optional dependency
    from bleak import BleakClient, BleakScanner
    from bleak.backends.device import BLEDevice as _BleakDevice
except Exception:  # pragma: no cover
    BleakClient = None  # type: ignore
    BleakScanner = None  # type: ignore
    _BleakDevice = None  # type: ignore

if TYPE_CHECKING:  # pragma: no cover - typing aid
    from bleak.backends.device import BLEDevice
    from bleak import BleakClient as BleakClientType
else:  # pragma: no cover
    BLEDevice = _BleakDevice  # type: ignore[assignment]
    BleakClientType = Any


logger = structlog.get_logger(__name__)


# BlueZ returns this error from Device.Connect() for GATT-only LE peripherals
# (like the DWARF): the LE link comes up and services resolve, but no classic
# profile attaches, so BlueZ reports "No more profiles to connect to". bleak
# treats it as fatal, while phones simply ignore it and use GATT directly.
_TOLERATED_BLUEZ_CONNECT_ERRORS = frozenset({"org.bluez.Error.BREDR.ProfileUnavailable"})

_bluez_workaround_installed = False


def _install_bluez_profile_workaround() -> None:
    """Make bleak's BlueZ backend ignore the spurious ProfileUnavailable error.

    Patches the ``assert_reply`` reference used by bleak's connect path so that
    the single ``BREDR.ProfileUnavailable`` error is swallowed (GATT is already
    usable at that point) while every other D-Bus failure still raises. No-op on
    non-Linux platforms and idempotent.
    """

    global _bluez_workaround_installed
    if _bluez_workaround_installed or not sys.platform.startswith("linux"):
        return
    try:  # pragma: no cover - depends on bleak's BlueZ backend being importable
        from bleak.backends.bluezdbus import client as bluez_client
    except Exception:  # pragma: no cover - non-BlueZ build
        return

    original_assert_reply = getattr(bluez_client, "assert_reply", None)
    if original_assert_reply is None:  # pragma: no cover - unexpected bleak layout
        return

    def _tolerant_assert_reply(reply: Any) -> None:
        if getattr(reply, "error_name", None) in _TOLERATED_BLUEZ_CONNECT_ERRORS:
            logger.warning(
                "ble.provision.bluez_profile_unavailable_ignored",
                error_name=getattr(reply, "error_name", None),
            )
            return
        original_assert_reply(reply)

    bluez_client.assert_reply = _tolerant_assert_reply
    _bluez_workaround_installed = True
    logger.info("ble.provision.bluez_profile_workaround_installed")


# Standard 16-bit Bluetooth SIG services we never want to send DWARF commands to
# (GAP, GATT, device info, PnP). Anything else is treated as a vendor/custom
# service and preferred when auto-selecting the command characteristic.
_STANDARD_SERVICE_PREFIXES = (
    "00001800",  # Generic Access
    "00001801",  # Generic Attribute
    "00001804",  # Tx Power
    "0000180a",  # Device Information
    "00001200",  # PnP Information
)


def _looks_custom_service(uuid: str) -> bool:
    normalized = uuid.lower()
    return not any(normalized.startswith(prefix) for prefix in _STANDARD_SERVICE_PREFIXES)


def _is_ble_device(candidate: Any) -> bool:
    return (
        candidate is not None
        and not isinstance(candidate, str)
        and hasattr(candidate, "address")
        and hasattr(candidate, "name")
    )


@dataclass
class ProvisioningResult:
    success: bool
    message: str
    sta_ip: str | None = None


class DwarfBleProvisioner:
    """BLE provisioning workflow for DWARF STA onboarding."""

    DEVICE_PREFIX = "DWARF"

    def __init__(self, *, response_timeout: float = 15.0) -> None:
        self.response_timeout = response_timeout
        # Resolved per-connection in _resolve_characteristic(); defaults to the
        # DWARF 3 characteristic so behaviour is unchanged if discovery is skipped.
        self._active_char_uuid = DWARF_CHARACTERISTIC_UUID
        _install_bluez_profile_workaround()

    def _resolve_characteristic(self, client: BleakClientType) -> str:
        """Pick the GATT characteristic to talk to, across DWARF models.

        The DWARF 3 exposes the command characteristic at
        ``00009999-…`` under service ``daf2``/``daf3``; the DWARF mini uses a
        different layout (service ``daf5``). Rather than hard-code per model,
        log the full GATT table and select a characteristic that supports both
        write and notify, preferring the known DWARF 3 UUID, then a custom
        (vendor) service, then any candidate. Falls back to the DWARF 3 UUID.
        """

        services = getattr(client, "services", None) or []
        default_present = False
        candidates: list[tuple[int, str]] = []
        for service in services:
            svc_uuid = str(service.uuid).lower()
            for ch in service.characteristics:
                ch_uuid = str(ch.uuid).lower()
                props = {p.lower() for p in ch.properties}
                logger.info(
                    "ble.provision.gatt_char",
                    service=svc_uuid,
                    characteristic=ch_uuid,
                    properties=sorted(props),
                )
                if ch_uuid == DWARF_CHARACTERISTIC_UUID:
                    default_present = True
                can_write = bool(props & {"write", "write-without-response"})
                can_notify = bool(props & {"notify", "indicate"})
                if can_write and can_notify:
                    priority = 0 if _looks_custom_service(svc_uuid) else 1
                    candidates.append((priority, ch_uuid))

        if default_present:
            chosen = DWARF_CHARACTERISTIC_UUID
            reason = "known-dwarf3-uuid"
        elif candidates:
            candidates.sort(key=lambda item: item[0])
            chosen = candidates[0][1]
            reason = "auto-discovered"
        else:
            chosen = DWARF_CHARACTERISTIC_UUID
            reason = "fallback-no-candidate"

        logger.info("ble.provision.characteristic_selected", characteristic=chosen, reason=reason)
        return chosen

    @staticmethod
    async def discover_devices(
        *, adapter: str | None = None, timeout: float = 10.0
    ) -> list[BLEDevice]:
        if BleakScanner is None:
            return []
        devices = await BleakScanner.discover(adapter=adapter, timeout=timeout)
        return [device for device in devices if device.name and device.name.startswith("DWARF")]

    async def provision(
        self,
        ssid: str,
        password: str,
        *,
        adapter: str | None = None,
        ble_password: str | None = None,
        timeout: float | None = None,
        device: BLEDevice | str | None = None,
    ) -> ProvisioningResult:
        if BleakScanner is None or BleakClient is None:
            return ProvisioningResult(False, "bleak library not available")

        device = await self._ensure_device(device, adapter=adapter)

        if device is None:
            return ProvisioningResult(False, "DWARF BLE device not found")

        ble_psd = ble_password or DEFAULT_BLE_PASSWORD
        deadline = asyncio.get_running_loop().time() + (timeout or 60.0)

        logger.info("ble.provision.connect", address=getattr(device, "address", None))
        async with BleakClient(device, adapter=adapter) as client:
            response_queue: asyncio.Queue[ParsedPacket] = asyncio.Queue()
            loop = asyncio.get_running_loop()

            def _notification_handler(_: int, data: bytearray) -> None:
                payload = bytes(data)

                def _put() -> None:
                    try:
                        packet = parse_notification(payload)
                    except BlePacketError as exc:
                        logger.warning("ble.provision.parse_error", error=str(exc))
                        return
                    response_queue.put_nowait(packet)

                loop.call_soon_threadsafe(_put)

            try:
                self._active_char_uuid = self._resolve_characteristic(client)
                await client.start_notify(self._active_char_uuid, _notification_handler)
                config = await self._write_and_wait_for_config(
                    client,
                    response_queue,
                    ble_psd=ble_psd,
                    deadline=deadline,
                )
                sta_ip = await self._configure_sta(
                    client,
                    response_queue,
                    current_config=config,
                    ssid=ssid,
                    password=password,
                    ble_psd=ble_psd,
                    deadline=deadline,
                )
                return ProvisioningResult(True, "Provisioning succeeded", sta_ip=sta_ip)
            except asyncio.TimeoutError:
                logger.error("ble.provision.timeout")
                return ProvisioningResult(False, "BLE provisioning timed out")
            except ProvisioningError as exc:
                logger.error("ble.provision.failed", error=str(exc))
                return ProvisioningResult(False, str(exc))
            except Exception as exc:  # pragma: no cover - hardware dependent
                logger.error("ble.provision.unexpected_error", error=str(exc))
                return ProvisioningResult(False, f"Provisioning failed: {exc}")
            finally:
                with contextlib.suppress(Exception):
                    await client.stop_notify(self._active_char_uuid)

    async def _discover_device(self, adapter: str | None) -> Optional[BLEDevice]:
        logger.info("ble.provision.scan", adapter=adapter)
        devices = await self.discover_devices(adapter=adapter)
        for device in devices:
            logger.info("ble.provision.device_found", name=device.name, address=device.address)
            return device
        logger.warning("ble.provision.device_missing")
        return None

    async def _resolve_device_by_address(
        self, address: str, *, adapter: str | None
    ) -> Optional[BLEDevice]:
        if BleakScanner is None:
            return None
        devices = await self.discover_devices(adapter=adapter)
        for device in devices:
            if device.address.lower() == address.lower():
                return device
        logger.warning("ble.provision.device_not_available", address=address)
        return None

    async def _ensure_device(
        self, device: BLEDevice | str | None, *, adapter: str | None
    ) -> Optional[BLEDevice]:
        if _is_ble_device(device):
            return cast(BLEDevice, device)
        if isinstance(device, str):
            return await self._resolve_device_by_address(device, adapter=adapter)
        return await self._discover_device(adapter=adapter)

    async def fetch_wifi_list(
        self,
        *,
        device: BLEDevice | str | None,
        adapter: str | None,
        ble_password: str,
        timeout: float | None = None,
    ) -> list[str]:
        if BleakScanner is None or BleakClient is None:
            raise ProvisioningError("BLE provisioning not available (bleak library not installed)")

        device_obj = await self._ensure_device(device, adapter=adapter)
        if device_obj is None:
            logger.warning("ble.provision.wifi.device_missing")
            return []

        loop = asyncio.get_running_loop()
        deadline = loop.time() + (timeout or 30.0)

        async with BleakClient(device_obj, adapter=adapter) as client:
            response_queue: asyncio.Queue[ParsedPacket] = asyncio.Queue()

            def _notification_handler(_: int, data: bytearray) -> None:
                payload = bytes(data)

                def _put() -> None:
                    try:
                        packet = parse_notification(payload)
                    except BlePacketError as exc:
                        logger.warning("ble.provision.wifi.parse_error", error=str(exc))
                        return
                    response_queue.put_nowait(packet)

                loop.call_soon_threadsafe(_put)

            self._active_char_uuid = self._resolve_characteristic(client)
            await client.start_notify(self._active_char_uuid, _notification_handler)
            try:
                await client.write_gatt_char(
                    self._active_char_uuid,
                    build_req_getconfig(ble_password),
                    response=True,
                )

                initial_packet = await self._await_packet(response_queue, {0, 1}, deadline)
                if initial_packet.cmd == 0:
                    message = initial_packet.payload  # type: ignore[assignment]
                    assert isinstance(message, ble_pb2.ResReceiveDataError)
                    raise ProvisioningError(
                        f"BLE error retrieving Wi-Fi list: {describe_ble_error(message.code)}"
                    )

                await client.write_gatt_char(
                    self._active_char_uuid,
                    build_req_getwifilist(),
                    response=True,
                )

                while True:
                    packet = await self._await_packet(response_queue, {0, 6}, deadline)
                    if packet.cmd == 0:
                        message = packet.payload  # type: ignore[assignment]
                        assert isinstance(message, ble_pb2.ResReceiveDataError)
                        raise ProvisioningError(
                            f"BLE error retrieving Wi-Fi list: {describe_ble_error(message.code)}"
                        )
                    if packet.cmd == 6:
                        wifi_response = packet.payload
                        assert isinstance(wifi_response, ble_pb2.ResWifilist)
                        return list(wifi_response.ssid)
            finally:
                with contextlib.suppress(Exception):
                    await client.stop_notify(self._active_char_uuid)

    async def _write_and_wait_for_config(
        self,
        client: BleakClientType,
        queue: asyncio.Queue[ParsedPacket],
        *,
        ble_psd: str,
        deadline: float,
    ) -> Any:
        await client.write_gatt_char(
            self._active_char_uuid,
            build_req_getconfig(ble_psd),
            response=True,
        )
        packet = await self._await_packet(queue, {0, 1}, deadline)
        if packet.cmd == 0:
            message = packet.payload  # type: ignore[assignment]
            assert isinstance(message, ble_pb2.ResReceiveDataError)
            raise ProvisioningError(
                f"BLE error during configuration query: {describe_ble_error(message.code)}"
            )

        message = packet.payload
        assert isinstance(message, ble_pb2.ResGetconfig)
        if message.code != 0:
            raise ProvisioningError(
                f"DWARF returned error: {describe_ble_error(message.code)}"
            )
        logger.info(
            "ble.provision.config", state=message.state, mode=message.wifi_mode, ip=message.ip
        )
        return message

    async def _configure_sta(
        self,
        client: BleakClientType,
        queue: asyncio.Queue[ParsedPacket],
        *,
    current_config: Any,
        ssid: str,
        password: str,
        ble_psd: str,
        deadline: float,
    ) -> Optional[str]:
        config = current_config

        if (
            config.state == 2
            and config.wifi_mode == 2
            and config.ssid == ssid
            and config.ip
            and config.ip != "192.168.88.1"
        ):
            logger.info("ble.provision.already_configured", ip=config.ip)
            return config.ip

        auto_start = 1 if config.state != 2 else 0
        logger.info(
            "ble.provision.send_sta", ssid=ssid, auto_start=auto_start
        )
        await client.write_gatt_char(
            self._active_char_uuid,
            build_req_sta(auto_start, ble_psd, ssid, password),
            response=True,
        )

        sta_ip: Optional[str] = None
        while True:
            packet = await self._await_packet(queue, {0, 1, 3}, deadline)
            if packet.cmd == 0:
                error_message = packet.payload  # type: ignore[assignment]
                assert isinstance(error_message, ble_pb2.ResReceiveDataError)
                raise ProvisioningError(
                    f"BLE error while configuring STA: {describe_ble_error(error_message.code)}"
                )
            if packet.cmd == 3:
                sta_response = packet.payload
                assert isinstance(sta_response, ble_pb2.ResSta)
                if sta_response.code != 0:
                    raise ProvisioningError(
                        f"DWARF STA provisioning failed: {describe_ble_error(sta_response.code)}"
                    )
                sta_ip = sta_response.ip or sta_ip
                if sta_ip and sta_ip != "192.168.88.1":
                    break
                logger.info("ble.provision.query_followup")
                await client.write_gatt_char(
                    self._active_char_uuid,
                    build_req_getconfig(ble_psd),
                    response=True,
                )
            if packet.cmd == 1:
                latest_config = packet.payload
                assert isinstance(latest_config, ble_pb2.ResGetconfig)
                if latest_config.code != 0:
                    raise ProvisioningError(
                        f"DWARF returned error: {describe_ble_error(latest_config.code)}"
                    )
                if (
                    latest_config.state == 2
                    and latest_config.wifi_mode == 2
                    and latest_config.ip
                    and latest_config.ip != "192.168.88.1"
                ):
                    sta_ip = latest_config.ip
                    break
        if not sta_ip:
            raise ProvisioningError("STA IP address not reported by DWARF after provisioning")
        return sta_ip

    async def _await_packet(
        self,
        queue: asyncio.Queue[ParsedPacket],
        expected_cmds: set[int],
        deadline: float,
    ) -> ParsedPacket:
        while True:
            loop = asyncio.get_running_loop()
            timeout = min(self.response_timeout, deadline - loop.time())
            if timeout <= 0:
                raise asyncio.TimeoutError
            packet = await asyncio.wait_for(queue.get(), timeout=timeout)
            if packet.cmd in expected_cmds:
                return packet
            logger.debug("ble.provision.ignore_packet", cmd=packet.cmd)


class ProvisioningError(RuntimeError):
    """Raised when provisioning fails with a DWARF-reported error."""
