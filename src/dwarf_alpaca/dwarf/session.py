from __future__ import annotations

import asyncio
import contextlib
import math
import time
from datetime import datetime
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, Optional, Tuple, Type

import numpy as np
import structlog
from google.protobuf.message import Message
from google.protobuf.json_format import MessageToDict

from ..config.settings import Settings
from ..proto import astro_pb2, protocol_pb2
from . import exposure
from ..proto.dwarf_messages import (
    CommonParam,
    ComResponse,
    ReqSetTime,
    ReqCloseCamera,
    ReqGetSystemWorkingState,
    ReqGotoDSO,
    ReqManualContinuFocus,
    ReqManualSingleStepFocus,
    ReqMotorRunTo,
    ReqMotorServiceJoystick,
    ReqMotorServiceJoystickStop,
    ReqPhotoRaw,
    ReqOpenCamera,
    ReqSetIrCut,
    ReqSetFeatureParams,
    ReqSetExp,
    ReqSetExpMode,
    ReqSetGain,
    ReqSetGainMode,
    ReqStopGoto,
    ReqStopManualContinuFocus,
    ReqsetMasterLock,
    ResNotifyFocus,
    ResNotifyHostSlaveMode,
    ResNotifyParam,
    ResNotifyTemperature,
)
from .ftp_client import DwarfFtpClient, FtpPhotoEntry
from .http_client import DwarfHttpClient
from .ws_client import DwarfCommandError, DwarfWsClient, send_and_check

logger = structlog.get_logger(__name__)


FALLBACK_FILTER_LABELS = ["VIS Filter", "Astro Filter", "Duo-Band Filter"]

_MAX_JOYSTICK_SPEED = 30.0
_MIN_JOYSTICK_SPEED = 0.1


def _canonical_filter_label(raw_label: str, index: int) -> str:
    cleaned = " ".join((raw_label or "").split())
    if not cleaned:
        return f"Filter {index}"
    return cleaned


def _message_to_log(message: Message) -> Dict[str, Any]:
    try:
        payload = MessageToDict(message, preserving_proto_field_name=True)
    except Exception as exc:  # pragma: no cover - defensive logging helper
        payload = {"_repr": repr(message), "_error": str(exc)}
    return payload


@dataclass
class CameraState:
    connected: bool = False
    start_time: float | None = None
    duration: float = 0.0
    light: bool = True
    capture_mode: str = "photo"
    filter_name: str = ""
    filter_index: int | None = None
    exposure_index: int | None = None
    image: Optional[np.ndarray] = field(default=None, repr=False)
    capture_task: asyncio.Task[None] | None = field(default=None, repr=False)
    last_start_time: float | None = None
    last_end_time: float | None = None
    frame_width: int = 0
    frame_height: int = 0
    image_timestamp: float | None = None
    last_error: str | None = None
    last_dark_check_code: int | None = None
    last_album_mod_time: int | None = None
    last_album_file: str | None = None
    pending_album_baseline: int | None = None
    last_ftp_entry: "FtpPhotoEntry | None" = field(default=None, repr=False)
    pending_ftp_baseline: "FtpPhotoEntry | None" = field(default=None, repr=False)
    temperature_c: float | None = None
    last_temperature_time: float | None = None
    last_temperature_code: int | None = None
    requested_gain: int | None = None
    applied_gain_index: int | None = None
    requested_bin: tuple[int, int] = (1, 1)
    requested_frame_count: int = 1


@dataclass
class FocuserState:
    connected: bool = False
    position: int = 0
    is_moving: bool = False
    last_update: float | None = None


@dataclass(frozen=True)
class FilterOption:
    parameter: dict[str, Any] | None
    mode_index: int
    index: int
    label: str
    continue_value: float | None = None
    controllable: bool = True


class DwarfSession:
    """Coordinates DWARF websocket and HTTP access for device routers."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.simulation = settings.force_simulation
        self._ws_client = DwarfWsClient(
            settings.dwarf_ap_ip,
            port=settings.dwarf_ws_port,
            major_version=1,
            minor_version=2,
            client_id=settings.dwarf_ws_client_id,
            ping_interval=settings.ws_ping_interval_seconds,
        )
        self._focus_update_event = asyncio.Event()
        self._ws_client.register_notification_handler(self._handle_notification)
        self._http_client = DwarfHttpClient(
            settings.dwarf_ap_ip,
            api_port=settings.dwarf_http_port,
            jpeg_port=settings.dwarf_jpeg_port,
            timeout=settings.http_timeout_seconds,
            retries=settings.http_retries,
        )
        self._ftp_client = DwarfFtpClient(
            settings.dwarf_ap_ip,
            port=settings.dwarf_ftp_port,
            timeout=settings.ftp_timeout_seconds,
            poll_interval=settings.ftp_poll_interval_seconds,
        )
        self._refs: dict[str, int] = {"telescope": 0, "camera": 0, "focuser": 0, "filterwheel": 0}
        self._master_lock_acquired = False
        self._master_lock_lock = asyncio.Lock()
        self._lock = asyncio.Lock()
        self._ws_command_lock = asyncio.Lock()
        self._ws_bootstrapped = False
        self.camera_state = CameraState()
        self.focuser_state = FocuserState()
        self._exposure_resolver: Optional[exposure.ExposureResolver] = None
        self._params_config: Optional[dict[str, Any]] = None
        self._filter_options: list[FilterOption] | None = None
        self._last_dark_check_code: int | None = None
        self._axis_direction_polarity = {0: 1, 1: 1}
        self._manual_axis_rates = {0: 0.0, 1: 0.0}
        self._joystick_active = False
        self._temperature_task = None  # type: asyncio.Task[None] | None
        self._last_goto_time: float | None = None
        self._last_goto_target: tuple[float, float] | None = None
        self._time_synced = self.simulation

    @property
    def is_simulated(self) -> bool:
        return self.simulation

    @property
    def has_master_lock(self) -> bool:
        return self._master_lock_acquired

    async def _ensure_ws(self) -> None:
        if self.simulation:
            return
        was_connected = self._ws_client.connected
        try:
            await self._ws_client.connect()
        except Exception as exc:  # pragma: no cover - hardware dependent
            logger.warning("dwarf.ws.connect_failed", error=str(exc))
            raise
        if not was_connected and self._ws_client.connected:
            self._master_lock_acquired = False
            self._ws_bootstrapped = False
            self._time_synced = self.simulation
        await self._ensure_master_lock()
        self._ensure_temperature_monitor_task()

    async def _bootstrap_ws(self) -> None:
        if self.simulation or self._ws_bootstrapped or not self._ws_client.connected:
            return

        commands = (
            (
                protocol_pb2.ModuleId.MODULE_CAMERA_TELE,
                protocol_pb2.DwarfCMD.CMD_CAMERA_TELE_GET_SYSTEM_WORKING_STATE,
                ReqGetSystemWorkingState,
            ),
            (
                protocol_pb2.ModuleId.MODULE_CAMERA_TELE,
                protocol_pb2.DwarfCMD.CMD_CAMERA_TELE_OPEN_CAMERA,
                ReqOpenCamera,
            ),
            (
                protocol_pb2.ModuleId.MODULE_CAMERA_WIDE,
                protocol_pb2.DwarfCMD.CMD_CAMERA_WIDE_OPEN_CAMERA,
                ReqOpenCamera,
            ),
        )

        expected = {
            (
                protocol_pb2.ModuleId.MODULE_SYSTEM,
                protocol_pb2.DwarfCMD.CMD_NOTIFY_WS_HOST_SLAVE_MODE,
            ): ResNotifyHostSlaveMode,
            (
                protocol_pb2.ModuleId.MODULE_NOTIFY,
                protocol_pb2.DwarfCMD.CMD_NOTIFY_WS_HOST_SLAVE_MODE,
            ): ResNotifyHostSlaveMode,
        }

        for module_id, command, message_cls in commands:
            message = message_cls()
            if isinstance(message, ReqOpenCamera):
                message.binning = False
                message.rtsp_encode_type = 0
            try:
                response = await self._send_command(
                    module_id,
                    command,
                    message,
                    timeout=10.0,
                    expected_responses=expected,
                )
                if isinstance(response, ResNotifyHostSlaveMode):
                    logger.info(
                        "dwarf.system.bootstrap_host_status module=%s cmd=%s mode=%s lock=%s",
                        module_id,
                        command,
                        getattr(response, "mode", None),
                        bool(getattr(response, "lock", False)),
                    )
                elif isinstance(response, ComResponse) and response.code != protocol_pb2.OK:
                    logger.warning(
                        "dwarf.system.bootstrap_command_nonzero module=%s cmd=%s code=%s",
                        module_id,
                        command,
                        response.code,
                    )
            except Exception as exc:  # pragma: no cover - hardware dependent
                logger.warning(
                    "dwarf.system.bootstrap_command_failed module=%s cmd=%s error=%s",
                    module_id,
                    command,
                    exc,
                )
                return
            await asyncio.sleep(0.2)

        self._ws_bootstrapped = True

    async def _handle_notification(self, packet: Message) -> None:
        module_id = getattr(packet, "module_id", None)
        if module_id != protocol_pb2.ModuleId.MODULE_NOTIFY:
            return
        command_id = getattr(packet, "cmd", None)
        if command_id == protocol_pb2.DwarfCMD.CMD_NOTIFY_FOCUS:
            self._handle_focus_notification(packet)
        elif command_id == protocol_pb2.DwarfCMD.CMD_NOTIFY_TEMPERATURE:
            self._handle_temperature_notification(packet)

    def _handle_focus_notification(self, packet: Message) -> None:
        raw_data = getattr(packet, "data", b"") or b""
        if not raw_data:
            return
        message = ResNotifyFocus()
        try:
            message.ParseFromString(raw_data)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.debug(
                "dwarf.focus.notification.decode_failed",
                error=str(exc),
            )
            return
        focus_value = getattr(message, "focus", None)
        if focus_value is None:
            return
        position = max(0, min(int(focus_value), 20000))
        state = self.focuser_state
        if state.position != position:
            logger.info("dwarf.focus.notification", position=position)
        state.position = position
        state.connected = True
        state.last_update = time.time()
        self._focus_update_event.set()

    def _handle_temperature_notification(self, packet: Message) -> None:
        raw_data = getattr(packet, "data", b"") or b""
        if not raw_data:
            return
        message = ResNotifyTemperature()
        try:
            message.ParseFromString(raw_data)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.debug(
                "dwarf.temperature.notification.decode_failed",
                error=str(exc),
            )
            return
        temperature_value = getattr(message, "temperature", None)
        if temperature_value is None:
            return
        temperature_c = float(temperature_value)
        code = getattr(message, "code", None)
        state = self.camera_state
        if state.temperature_c != temperature_c:
            logger.info("dwarf.temperature.notification", temperature=temperature_c)
        state.temperature_c = temperature_c
        state.last_temperature_time = time.time()
        state.last_temperature_code = code
        if code not in (None, protocol_pb2.OK):
            logger.warning(
                "dwarf.temperature.notification.code_nonzero",
                code=code,
                temperature=temperature_c,
            )

    def _ensure_temperature_monitor_task(self) -> None:
        task = self._temperature_task
        if task and task.done():
            with contextlib.suppress(Exception):
                task.result()
            self._temperature_task = None

        if self.simulation:
            return
        if self.settings.temperature_refresh_interval_seconds <= 0:
            return
        if self._temperature_task is None:
            self._temperature_task = asyncio.create_task(self._temperature_monitor_loop())

    async def _temperature_monitor_loop(self) -> None:
        try:
            while True:
                interval = self.settings.temperature_refresh_interval_seconds
                if interval <= 0:
                    await asyncio.sleep(1.0)
                    continue

                if not self.simulation and self._ws_client.connected and self.camera_state.connected:
                    stale_after = self.settings.temperature_stale_after_seconds
                    last_update = self.camera_state.last_temperature_time
                    now = time.time()
                    is_stale = last_update is None
                    if not is_stale and stale_after > 0:
                        is_stale = now - last_update >= stale_after

                    if is_stale:
                        try:
                            await self._request_temperature_update()
                        except asyncio.CancelledError:
                            raise
                        except Exception as exc:  # pragma: no cover - hardware dependent
                            logger.debug("dwarf.temperature.refresh_failed", error=str(exc))

                try:
                    await asyncio.sleep(interval)
                except asyncio.CancelledError:
                    raise
        except asyncio.CancelledError:
            logger.debug("dwarf.temperature.monitor.cancelled")
            raise

    async def _request_temperature_update(self) -> None:
        await self._ensure_ws()
        request = ReqGetSystemWorkingState()
        expected_responses = {
            (
                protocol_pb2.ModuleId.MODULE_SYSTEM,
                protocol_pb2.DwarfCMD.CMD_NOTIFY_WS_HOST_SLAVE_MODE,
            ): ResNotifyHostSlaveMode,
            (
                protocol_pb2.ModuleId.MODULE_NOTIFY,
                protocol_pb2.DwarfCMD.CMD_NOTIFY_WS_HOST_SLAVE_MODE,
            ): ResNotifyHostSlaveMode,
        }
        try:
            await self._send_command(
                protocol_pb2.ModuleId.MODULE_CAMERA_TELE,
                protocol_pb2.DwarfCMD.CMD_CAMERA_TELE_GET_SYSTEM_WORKING_STATE,
                request,
                timeout=5.0,
                expected_responses=expected_responses,
            )
            logger.debug("dwarf.temperature.refresh_requested")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.debug("dwarf.temperature.refresh_command_failed", error=str(exc))
            raise

    async def _send_and_check(
        self,
        module_id: int,
        command_id: int,
        request: Message,
        *,
        timeout: float = 10.0,
        expected_responses: Optional[Dict[Tuple[int, int], Type[Message]]] = None,
    ) -> None:
        async with self._ws_command_lock:
            expected_summary = {
                f"{mid}:{cid}": resp_cls.__name__
                for (mid, cid), resp_cls in (expected_responses or {}).items()
            }
            logger.info(
                "dwarf.ws.command.send_and_check",
                module_id=module_id,
                command_id=command_id,
                timeout=timeout,
                request_type=request.__class__.__name__,
                request_payload=_message_to_log(request),
                expected_responses=expected_summary,
            )
            await send_and_check(
                self._ws_client,
                module_id,
                command_id,
                request,
                timeout=timeout,
                expected_responses=expected_responses,
            )
            logger.info(
                "dwarf.ws.command.send_and_check.completed",
                module_id=module_id,
                command_id=command_id,
            )

    async def _send_request(
        self,
        module_id: int,
        command_id: int,
        request: Message,
        response_cls: Type[Message],
        *,
        timeout: float = 10.0,
        expected_responses: Optional[Dict[Tuple[int, int], Type[Message]]] = None,
    ) -> Message:
        async with self._ws_command_lock:
            expected_summary = {
                f"{mid}:{cid}": resp_cls.__name__
                for (mid, cid), resp_cls in (expected_responses or {}).items()
            }
            logger.info(
                "dwarf.ws.command.send",
                module_id=module_id,
                command_id=command_id,
                timeout=timeout,
                request_type=request.__class__.__name__,
                request_payload=_message_to_log(request),
                expected_responses=expected_summary,
                expected_response_type=response_cls.__name__,
            )
            response = await self._ws_client.send_request(
                module_id,
                command_id,
                request,
                response_cls,
                timeout=timeout,
                expected_responses=expected_responses,
            )
            logger.info(
                "dwarf.ws.command.response",
                module_id=module_id,
                command_id=command_id,
                response_type=response.__class__.__name__,
                response_payload=_message_to_log(response),
                response_code=getattr(response, "code", None),
            )
            return response

    async def _send_command(
        self,
        module_id: int,
        command_id: int,
        request: Message,
        *,
        timeout: float = 10.0,
        expected_responses: Optional[Dict[Tuple[int, int], Type[Message]]] = None,
    ) -> Message:
        return await self._send_request(
            module_id,
            command_id,
            request,
            ComResponse,
            timeout=timeout,
            expected_responses=expected_responses,
        )

    async def _ensure_master_lock(self) -> None:
        if self.simulation or self._master_lock_acquired:
            return
        async with self._master_lock_lock:
            if self.simulation or self._master_lock_acquired:
                return
            if not self._ws_client.connected:
                return
            await self._bootstrap_ws()
            request = ReqsetMasterLock()
            request.lock = True
            expected_responses = {
                (
                    protocol_pb2.ModuleId.MODULE_SYSTEM,
                    protocol_pb2.DwarfCMD.CMD_NOTIFY_WS_HOST_SLAVE_MODE,
                ): ResNotifyHostSlaveMode,
                (
                    protocol_pb2.ModuleId.MODULE_NOTIFY,
                    protocol_pb2.DwarfCMD.CMD_NOTIFY_WS_HOST_SLAVE_MODE,
                ): ResNotifyHostSlaveMode,
            }
            try:
                response = await self._ws_client.send_request(
                    protocol_pb2.ModuleId.MODULE_SYSTEM,
                    protocol_pb2.DwarfCMD.CMD_SYSTEM_SET_MASTERLOCK,
                    request,
                    ComResponse,
                    timeout=15.0,
                    expected_responses=expected_responses,
                )

                if isinstance(response, ComResponse):
                    if response.code != protocol_pb2.OK:
                        raise DwarfCommandError(
                            protocol_pb2.ModuleId.MODULE_SYSTEM,
                            protocol_pb2.DwarfCMD.CMD_SYSTEM_SET_MASTERLOCK,
                            response.code,
                        )
                    self._master_lock_acquired = True
                    logger.info(
                        "dwarf.system.master_lock_acquired ip=%s",
                        self.settings.dwarf_ap_ip,
                    )
                elif isinstance(response, ResNotifyHostSlaveMode):
                    mode = getattr(response, "mode", None)
                    lock = bool(getattr(response, "lock", False))
                    if mode == 0 and lock:
                        self._master_lock_acquired = True
                        logger.info(
                            "dwarf.system.master_lock_acquired ip=%s mode=%s lock=%s",
                            self.settings.dwarf_ap_ip,
                            mode,
                            lock,
                        )
                    else:
                        logger.warning(
                            "dwarf.system.master_lock_unlocked ip=%s mode=%s lock=%s",
                            self.settings.dwarf_ap_ip,
                            mode,
                            lock,
                        )
                else:
                    logger.warning(
                        "dwarf.system.master_lock_unhandled_response ip=%s response_type=%s",
                        self.settings.dwarf_ap_ip,
                        type(response).__name__,
                    )
            except DwarfCommandError as exc:  # pragma: no cover - hardware dependent
                logger.warning(
                    "dwarf.system.master_lock_failed ip=%s code=%s",
                    self.settings.dwarf_ap_ip,
                    exc.code,
                )
            except Exception as exc:  # pragma: no cover - hardware dependent
                logger.warning(
                    "dwarf.system.master_lock_failed ip=%s error=%s error_type=%s error_repr=%r",
                    self.settings.dwarf_ap_ip,
                    exc,
                    type(exc).__name__,
                    exc,
                )

            if self._master_lock_acquired:
                await self._sync_device_clock()

    async def _release_master_lock(self) -> None:
        if self.simulation:
            self._master_lock_acquired = False
            return

        async with self._master_lock_lock:
            if not self._master_lock_acquired:
                return

            if not self._ws_client.connected:
                try:
                    await self._ws_client.connect()
                except Exception as exc:  # pragma: no cover - hardware dependent
                    logger.warning(
                        "dwarf.system.master_lock_disconnect",
                        error=str(exc),
                        error_type=type(exc).__name__,
                    )
                    self._master_lock_acquired = False
                    return

            request = ReqsetMasterLock()
            request.lock = False
            expected_responses = {
                (
                    protocol_pb2.ModuleId.MODULE_SYSTEM,
                    protocol_pb2.DwarfCMD.CMD_NOTIFY_WS_HOST_SLAVE_MODE,
                ): ResNotifyHostSlaveMode,
                (
                    protocol_pb2.ModuleId.MODULE_NOTIFY,
                    protocol_pb2.DwarfCMD.CMD_NOTIFY_WS_HOST_SLAVE_MODE,
                ): ResNotifyHostSlaveMode,
            }

            try:
                response = await self._ws_client.send_request(
                    protocol_pb2.ModuleId.MODULE_SYSTEM,
                    protocol_pb2.DwarfCMD.CMD_SYSTEM_SET_MASTERLOCK,
                    request,
                    ComResponse,
                    timeout=10.0,
                    expected_responses=expected_responses,
                )

                if isinstance(response, ComResponse):
                    if response.code != protocol_pb2.OK:
                        logger.warning(
                            "dwarf.system.master_lock_release_failed",
                            code=response.code,
                        )
                    else:
                        logger.info(
                            "dwarf.system.master_lock_released",
                            ip=self.settings.dwarf_ap_ip,
                        )
                elif isinstance(response, ResNotifyHostSlaveMode):
                    logger.info(
                        "dwarf.system.master_lock_unlocked",
                        ip=self.settings.dwarf_ap_ip,
                        mode=getattr(response, "mode", None),
                        lock=bool(getattr(response, "lock", False)),
                    )
                else:
                    logger.warning(
                        "dwarf.system.master_lock_release_unhandled_response",
                        ip=self.settings.dwarf_ap_ip,
                        response_type=type(response).__name__,
                    )
            except DwarfCommandError as exc:  # pragma: no cover - hardware dependent
                logger.warning(
                    "dwarf.system.master_lock_release_failed",
                    code=exc.code,
                )
            except Exception as exc:  # pragma: no cover - hardware dependent
                logger.warning(
                    "dwarf.system.master_lock_release_error",
                    error=str(exc),
                    error_type=type(exc).__name__,
                )
            finally:
                self._master_lock_acquired = False

    async def _sync_device_clock(self) -> None:
        """Push the current host timestamp and timezone offset to the DWARF device."""

        if self.simulation or self._time_synced:
            return

        request = ReqSetTime()
        timestamp = int(time.time())
        request.timestamp = timestamp

        local_time = datetime.now()
        utc_time = datetime.utcnow()
        offset_hours = (local_time - utc_time).total_seconds() / 3600.0
        timezone_offset = round(offset_hours * 4.0) / 4.0
        request.timezone_offset = timezone_offset

        try:
            await self._send_and_check(
                protocol_pb2.ModuleId.MODULE_SYSTEM,
                protocol_pb2.DwarfCMD.CMD_SYSTEM_SET_TIME,
                request,
                timeout=5.0,
            )
        except Exception as exc:  # pragma: no cover - hardware dependent
            logger.warning(
                "dwarf.system.time_sync_failed",
                error=str(exc),
                timestamp=timestamp,
                timezone_offset=timezone_offset,
                offset_raw=offset_hours,
            )
            return

        self._time_synced = True
        logger.info(
            "dwarf.system.time_synced",
            timestamp=timestamp,
            timezone_offset=timezone_offset,
            offset_raw=offset_hours,
        )

    async def acquire(self, device: str) -> None:
        async with self._lock:
            self._refs[device] += 1
            try:
                await self._ensure_ws()
            except Exception:
                self._refs[device] = max(0, self._refs[device] - 1)
                raise

    async def release(self, device: str) -> None:
        async with self._lock:
            self._refs[device] = max(0, self._refs[device] - 1)
            if not self.simulation and all(count == 0 for count in self._refs.values()):
                await self._ws_client.close()
                await self._http_client.aclose()
                self._master_lock_acquired = False

    async def shutdown(self) -> None:
        if self.camera_state.capture_task and not self.camera_state.capture_task.done():
            self.camera_state.capture_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.camera_state.capture_task
        self.camera_state.capture_task = None

        temperature_task = self._temperature_task
        if temperature_task:
            temperature_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await temperature_task
            self._temperature_task = None

        await self._release_master_lock()

        if not self.simulation:
            await self._ws_client.close()
            await self._http_client.aclose()

        self._master_lock_acquired = False
        self._ws_bootstrapped = False
        for key in self._refs:
            self._refs[key] = 0

    # --- Telescope -----------------------------------------------------------------

    async def telescope_slew_to_coordinates(
        self,
        ra_hours: float,
        dec_degrees: float,
        *,
        target_name: str = "Custom",
    ) -> tuple[float, float]:
        if self.simulation:
            self._record_goto(ra_hours, dec_degrees)
            return ra_hours, dec_degrees

        await self._ensure_ws()
        await self._halt_manual_motion()
        try:
            await self._start_goto_command(ra_hours, dec_degrees, target_name)
        except DwarfCommandError as exc:
            if exc.code != -11501:  # CODE_ASTRO_FUNCTION_BUSY
                raise
            logger.info(
                "dwarf.telescope.goto.busy",
                ra_hours=ra_hours,
                dec_degrees=dec_degrees,
                code=exc.code,
            )
            await self.telescope_abort_slew()
            await asyncio.sleep(0.2)
            await self._halt_manual_motion()
            await self._start_goto_command(ra_hours, dec_degrees, target_name)
        return ra_hours, dec_degrees

    async def telescope_move_axis(self, axis: int, rate: float) -> None:
        if axis not in (0, 1):
            raise ValueError(f"Unsupported axis {axis}")

        clamped_rate = max(min(rate, _MAX_JOYSTICK_SPEED), -_MAX_JOYSTICK_SPEED)
        manual_motion = abs(clamped_rate) >= 1e-6
        if self.simulation:
            self._manual_axis_rates[axis] = 0.0 if abs(clamped_rate) < 1e-6 else clamped_rate
            return

        if not manual_motion:
            await self.telescope_stop_axis(axis)
            return

        await self._ensure_ws()
        self._manual_axis_rates[axis] = clamped_rate
        logger.info(
            "dwarf.telescope.moveaxis.command",
            axis=axis,
            rate=clamped_rate,
            axes=dict(self._manual_axis_rates),
        )
        await self._send_manual_vector()

    async def telescope_stop_axis(self, axis: int, *, ensure_ws: bool = True) -> None:
        if axis not in (0, 1):
            raise ValueError(f"Unsupported axis {axis}")
        if self.simulation:
            self._manual_axis_rates[axis] = 0.0
            return
        if ensure_ws:
            await self._ensure_ws()

        if abs(self._manual_axis_rates.get(axis, 0.0)) < 1e-6 and not self._joystick_active:
            return

        self._manual_axis_rates[axis] = 0.0
        logger.info(
            "dwarf.telescope.stopaxis.command",
            axis=axis,
            axes=dict(self._manual_axis_rates),
        )
        await self._send_manual_vector()

    async def _send_manual_vector(self) -> None:
        rate_x = self._manual_axis_rates[0] * self._axis_direction_polarity.get(0, 1)
        rate_y = self._manual_axis_rates[1] * self._axis_direction_polarity.get(1, 1)
        magnitude = math.hypot(rate_x, rate_y)

        if magnitude < 1e-6:
            if self._joystick_active:
                await self._send_joystick_stop()
            return

        speed = max(min(magnitude, _MAX_JOYSTICK_SPEED), _MIN_JOYSTICK_SPEED)
        vector_length = min(1.0, magnitude / speed) if speed > 1e-6 else 0.0
        angle = math.degrees(math.atan2(rate_y, rate_x))
        if angle < 0.0:
            angle += 360.0

        request = ReqMotorServiceJoystick()
        request.vector_angle = angle
        request.vector_length = vector_length
        request.speed = speed

        try:
            await self._send_and_check(
                protocol_pb2.ModuleId.MODULE_MOTOR,
                protocol_pb2.DwarfCMD.CMD_STEP_MOTOR_SERVICE_JOYSTICK,
                request,
            )
        except DwarfCommandError as exc:
            logger.warning(
                "dwarf.telescope.manual_vector.failed",
                axes=dict(self._manual_axis_rates),
                vector_angle=angle,
                vector_length=vector_length,
                speed=speed,
                error_code=exc.code,
            )
            raise
        else:
            self._joystick_active = True
            logger.info(
                "dwarf.telescope.manual_vector",
                axes=dict(self._manual_axis_rates),
                vector_angle=angle,
                vector_length=vector_length,
                speed=speed,
            )

    async def _send_joystick_stop(self) -> None:
        request = ReqMotorServiceJoystickStop()
        try:
            await self._send_and_check(
                protocol_pb2.ModuleId.MODULE_MOTOR,
                protocol_pb2.DwarfCMD.CMD_STEP_MOTOR_SERVICE_JOYSTICK_STOP,
                request,
            )
        except DwarfCommandError as exc:
            logger.warning(
                "dwarf.telescope.manual_vector.stop_failed",
                error_code=exc.code,
            )
            raise
        else:
            self._joystick_active = False
            logger.info("dwarf.telescope.manual_vector.stopped")

    async def _halt_manual_motion(self) -> None:
        if self.simulation:
            return
        await self._ensure_ws()
        for axis in (0, 1):
            with contextlib.suppress(Exception):
                await self.telescope_stop_axis(axis, ensure_ws=False)

    def _record_goto(self, ra_hours: float, dec_degrees: float) -> None:
        self._last_goto_time = time.time()
        self._last_goto_target = (ra_hours, dec_degrees)
        logger.debug(
            "dwarf.telescope.goto_recorded",
            ra_hours=ra_hours,
            dec_degrees=dec_degrees,
        )

    def _clear_goto(self, *, reason: str | None = None) -> None:
        if self._last_goto_time is None:
            return
        logger.debug(
            "dwarf.telescope.goto_cleared",
            reason=reason,
            last_target=self._last_goto_target,
        )
        self._last_goto_time = None
        self._last_goto_target = None

    def _has_recent_goto(self) -> bool:
        max_age_value = self.settings.goto_valid_seconds
        max_age = float(max_age_value) if max_age_value is not None else 0.0
        if max_age <= 0.0:
            return True
        if self._last_goto_time is None:
            return False
        return (time.time() - self._last_goto_time) <= max_age

    async def _start_goto_command(
        self,
        ra_hours: float,
        dec_degrees: float,
        target_name: str,
    ) -> None:
        request = ReqGotoDSO()
        request.ra = ra_hours * 15.0  # DWARF expects degrees
        request.dec = dec_degrees
        request.target_name = target_name
        await self._send_and_check(
            protocol_pb2.ModuleId.MODULE_ASTRO,
            protocol_pb2.DwarfCMD.CMD_ASTRO_START_GOTO_DSO,
            request,
        )
        self._record_goto(ra_hours, dec_degrees)

    async def telescope_abort_slew(self) -> None:
        self._clear_goto(reason="slew_aborted")
        if self.simulation:
            return
        await self._ensure_ws()
        request = ReqStopGoto()
        await self._send_and_check(
            protocol_pb2.ModuleId.MODULE_ASTRO,
            protocol_pb2.DwarfCMD.CMD_ASTRO_STOP_GOTO,
            request,
        )
        for axis in (0, 1):
            with contextlib.suppress(Exception):
                await self.telescope_stop_axis(axis, ensure_ws=False)

    # --- Camera --------------------------------------------------------------------

    async def camera_connect(self) -> None:
        self.camera_state.connected = True
        if self.simulation:
            return
        await self._ensure_ws()
        request = ReqOpenCamera()
        request.binning = False
        request.rtsp_encode_type = 0
        await self._send_and_check(
            protocol_pb2.ModuleId.MODULE_CAMERA_TELE,
            protocol_pb2.DwarfCMD.CMD_CAMERA_TELE_OPEN_CAMERA,
            request,
        )

    async def camera_disconnect(self) -> None:
        if self.camera_state.capture_task and not self.camera_state.capture_task.done():
            self.camera_state.capture_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.camera_state.capture_task
        self.camera_state.capture_task = None
        self.camera_state.connected = False
        self.camera_state.image = None
        self.camera_state.start_time = None
        if self.simulation:
            return
        await self._ensure_ws()
        request = ReqCloseCamera()
        await self._send_and_check(
            protocol_pb2.ModuleId.MODULE_CAMERA_TELE,
            protocol_pb2.DwarfCMD.CMD_CAMERA_TELE_CLOSE_CAMERA,
            request,
        )

    async def camera_start_exposure(
        self,
        duration: float,
        light: bool,
        *,
        continue_without_darks: bool | None = None,
    ) -> None:
        state = self.camera_state
        state.duration = duration
        state.light = light
        state.start_time = time.time()
        state.last_start_time = state.start_time
        state.last_end_time = None
        state.image_timestamp = None
        state.last_error = None
        state.image = None
        state.last_dark_check_code = None
        state.capture_mode = "astro"
        frames_to_capture = max(1, int(state.requested_frame_count or 1))
        state.requested_frame_count = frames_to_capture
        if state.capture_task and not state.capture_task.done():
            state.capture_task.cancel()
        if self.simulation:
            await self._simulate_capture(state)
            state.capture_task = None
            return

        if continue_without_darks is None:
            continue_without_darks = self.settings.allow_continue_without_darks

        await self._ensure_ws()
        await self._ensure_exposure_settings(duration)
        await self._ensure_gain_settings()
        await self._ensure_selected_filter()

        command_timeout = max(duration + 10.0, 20.0)
        bin_x, bin_y = state.requested_bin or (1, 1)
        try:
            bin_x = max(1, int(bin_x))
            bin_y = max(1, int(bin_y))
        except (TypeError, ValueError):
            bin_x, bin_y = (1, 1)
        state.requested_bin = (bin_x, bin_y)

        if light and self.settings.go_live_before_exposure:
            await self._astro_go_live()

        dark_ready = True
        if light:
            try:
                dark_ready = await self._ensure_dark_library(continue_without_darks=continue_without_darks)
            except DwarfCommandError as exc:
                state.last_error = f"dark_check_error:{exc.code}"
                logger.error(
                    "dwarf.camera.dark_library_required",
                    code=exc.code,
                    continue_without_darks=continue_without_darks,
                )
                raise
            if not dark_ready:
                state.last_error = "dark_missing"
                logger.warning(
                    "dwarf.camera.dark_library_missing_continuing",
                    duration=duration,
                    continue_without_darks=continue_without_darks,
                )

        if light and not self._has_recent_goto():
            logger.warning(
                "dwarf.camera.astro_capture_goto_missing",
                duration=duration,
                light=light,
                goto_valid_seconds=self.settings.goto_valid_seconds,
                last_goto_time=self._last_goto_time,
                last_goto_target=self._last_goto_target,
                ignored=True,
            )

        await self._configure_astro_capture(frames=frames_to_capture, binning=(bin_x, bin_y))
        await self._refresh_capture_baseline(capture_kind=state.capture_mode)

        astro_code = protocol_pb2.OK
        try:
            astro_code = await self._start_astro_capture(timeout=command_timeout)
        except DwarfCommandError as exc:
            if exc.code == protocol_pb2.CODE_ASTRO_FUNCTION_BUSY:
                state.last_error = "astro_busy"
            else:
                state.last_error = f"command_error:{exc.code}"
            raise

        if astro_code not in (protocol_pb2.OK, protocol_pb2.CODE_ASTRO_NEED_GOTO):
            if astro_code == protocol_pb2.CODE_ASTRO_FUNCTION_BUSY:
                state.last_error = "astro_busy"
            else:
                state.last_error = f"command_error:{astro_code}"
            raise DwarfCommandError(
                protocol_pb2.ModuleId.MODULE_ASTRO,
                protocol_pb2.DwarfCMD.CMD_ASTRO_START_CAPTURE_RAW_LIVE_STACKING,
                astro_code,
            )

        if astro_code == protocol_pb2.CODE_ASTRO_NEED_GOTO:
            logger.warning(
                "dwarf.camera.astro_capture_goto_response",
                duration=duration,
                light=light,
                goto_target=self._last_goto_target,
            )

        state.last_error = None
        logger.info(
            "dwarf.camera.astro_capture_started",
            duration=duration,
            light=light,
            dark_ready=dark_ready,
            goto_target=self._last_goto_target,
            frames=frames_to_capture,
            binning=(bin_x, bin_y),
        )
        state.capture_task = asyncio.create_task(self._fetch_capture(state))

    async def camera_abort_exposure(self) -> None:
        state = self.camera_state
        if state.capture_task and not state.capture_task.done():
            state.capture_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await state.capture_task
        state.capture_task = None
        state.start_time = None
        state.image = None
        state.last_end_time = time.time()
        state.image_timestamp = None
        state.last_error = "aborted"
        if not self.simulation and state.capture_mode == "astro":
            await self._stop_astro_capture()

    async def camera_readout(self) -> Optional[np.ndarray]:
        return self.camera_state.image

    async def _ensure_exposure_settings(self, duration: float) -> None:
        if self.simulation:
            return
        state = self.camera_state
        resolver = await self._get_exposure_resolver()
        index = resolver.choose_index(duration) if resolver else None
        if index is None:
            logger.warning("dwarf.camera.exposure_index_missing", requested_duration=duration)
            return
        try:
            await self._set_exposure_mode_manual()
            await self._set_exposure_index(index)
        except DwarfCommandError as exc:  # pragma: no cover - hardware dependent
            logger.warning(
                "dwarf.camera.exposure_config_failed",
                error_code=getattr(exc, "code", None),
                module_id=getattr(exc, "module_id", None),
                command_id=getattr(exc, "command_id", None),
                requested_duration=duration,
                index=index,
            )
            if state.exposure_index is not None:
                logger.info(
                    "dwarf.camera.exposure_config_reusing_previous",
                    index=state.exposure_index,
                    requested_duration=duration,
                )
        except Exception as exc:  # pragma: no cover - hardware dependent
            logger.warning(
                "dwarf.camera.exposure_config_failed",
                error=str(exc),
                error_type=type(exc).__name__,
                requested_duration=duration,
                index=index,
            )
        else:
            state.exposure_index = index

    async def _ensure_params_config(self) -> Optional[dict[str, Any]]:
        if self._params_config is not None:
            return self._params_config
        try:
            payload = await self._http_client.get_default_params_config()
        except Exception as exc:  # pragma: no cover - hardware dependent
            logger.warning("dwarf.camera.params_config_fetch_failed", error=str(exc))
            self._params_config = None
            return None
        self._params_config = payload
        self._filter_options = None
        return payload

    async def _get_exposure_resolver(self) -> Optional[exposure.ExposureResolver]:
        if self._exposure_resolver is not None:
            return self._exposure_resolver
        payload = await self._ensure_params_config()
        if payload is None:
            self._exposure_resolver = None
            return None
        resolver = exposure.ExposureResolver.from_config(payload)
        if resolver is None:
            logger.warning("dwarf.camera.params_config_parse_failed")
        self._exposure_resolver = resolver
        return resolver

    def _find_feature_param(self, name: str) -> dict[str, Any] | None:
        needle = name.strip().lower()
        if not needle:
            return None
        for entry in self._iter_feature_params():
            entry_name = str(entry.get("name", "")).strip().lower()
            if entry_name == needle:
                return entry
        return None

    def _find_feature_param_contains(self, substring: str) -> dict[str, Any] | None:
        haystack = substring.strip().lower()
        if not haystack:
            return None
        for entry in self._iter_feature_params():
            entry_name = str(entry.get("name", "")).strip().lower()
            if haystack in entry_name:
                return entry
        return None

    def _iter_feature_params(self) -> Iterator[dict[str, Any]]:
        if not self._params_config:
            return
        data = self._params_config.get("data")
        if not isinstance(data, dict):
            return
        params = data.get("featureParams")
        if not isinstance(params, list):
            return
        for entry in params:
            if isinstance(entry, dict):
                yield entry

    @staticmethod
    def _tele_param_expected_responses() -> Dict[Tuple[int, int], Type[Message]]:
        return {
            (
                protocol_pb2.ModuleId.MODULE_NOTIFY,
                protocol_pb2.DwarfCMD.CMD_NOTIFY_TELE_SET_PARAM,
            ): ResNotifyParam,
        }

    def _iter_camera_support_params(
        self,
        *,
        camera_name: str | None = None,
    ) -> Iterator[tuple[str, dict[str, Any]]]:
        if not self._params_config:
            return
        data = self._params_config.get("data")
        if not isinstance(data, dict):
            return
        cameras = data.get("cameras")
        if not isinstance(cameras, list):
            return
        name_filter = camera_name.strip().lower() if camera_name else None
        for camera in cameras:
            if not isinstance(camera, dict):
                continue
            raw_name = str(camera.get("name", ""))
            resolved_name = raw_name.strip()
            lowered = resolved_name.lower()
            if name_filter and lowered != name_filter:
                continue
            params = camera.get("supportParams")
            if not isinstance(params, list):
                continue
            for param in params:
                if isinstance(param, dict):
                    yield resolved_name, param

    def _find_support_param_contains(
        self,
        substring: str,
        *,
        camera_name: str | None = None,
    ) -> dict[str, Any] | None:
        needle = substring.strip().lower()
        if not needle:
            return None
        for _, param in self._iter_camera_support_params(camera_name=camera_name):
            name = str(param.get("name", "")).strip().lower()
            if needle in name:
                return param
        return None

    @staticmethod
    def _resolve_support_mode_index(param: dict[str, Any], label_substring: str) -> int | None:
        haystack = label_substring.strip().lower()
        if not haystack:
            return None
        modes = param.get("supportMode")
        if not isinstance(modes, list):
            return None
        for entry in modes:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name", "")).strip().lower()
            if haystack in name:
                try:
                    return int(entry.get("index", 0))
                except (TypeError, ValueError):
                    continue
        return None

    @classmethod
    def _extract_support_param_options(
        cls,
        param: dict[str, Any],
    ) -> list[tuple[int | None, int, str, float | None]]:
        options: list[tuple[int | None, int, str, float | None]] = []
        gear_mode = param.get("gearMode")
        gear_mode_index = cls._resolve_support_mode_index(param, "gear")
        if isinstance(gear_mode, dict):
            values = gear_mode.get("values")
            if isinstance(values, list):
                for entry in values:
                    if not isinstance(entry, dict):
                        continue
                    try:
                        index_value = int(entry.get("index"))
                    except (TypeError, ValueError):
                        continue
                    label = str(entry.get("name", ""))
                    options.append((gear_mode_index, index_value, label, None))
        continue_mode = param.get("continueMode")
        continue_mode_index = cls._resolve_support_mode_index(param, "continue")
        if isinstance(continue_mode, dict) and continue_mode_index is not None:
            value = continue_mode.get("defaultValue")
            if isinstance(value, (int, float)):
                options.append((continue_mode_index, 0, str(value), float(value)))
        return options

    @staticmethod
    def _extract_feature_options(feature: dict[str, Any]) -> list[tuple[int | None, int, str, float | None]]:
        options: list[tuple[int | None, int, str, float | None]] = []

        def _coerce_float(value: Any) -> float | None:
            if isinstance(value, (int, float)):
                return float(value)
            if isinstance(value, str):
                try:
                    return float(value)
                except ValueError:
                    return None
            return None

        def _walk(node: Any, mode_index: int | None) -> None:
            current_mode = mode_index
            if isinstance(node, dict):
                if "modeIndex" in node:
                    try:
                        current_mode = int(node["modeIndex"])
                    except (TypeError, ValueError):
                        current_mode = mode_index
                has_index = "index" in node and "name" in node
                if has_index:
                    try:
                        index_value = int(node["index"])
                    except (TypeError, ValueError):
                        index_value = None
                    if index_value is not None:
                        label = str(node.get("name", ""))
                        continue_raw = (
                            node.get("continueValue")
                            if "continueValue" in node
                            else node.get("value")
                        )
                        continue_value = _coerce_float(continue_raw)
                        options.append((current_mode, index_value, label, continue_value))
                for value in node.values():
                    if isinstance(value, (dict, list)):
                        _walk(value, current_mode)
            elif isinstance(node, list):
                for item in node:
                    if isinstance(item, (dict, list)):
                        _walk(item, mode_index)

        _walk(feature, None)
        return options

    def _find_feature_option_by_label(
        self,
        label_substring: str,
    ) -> tuple[dict[str, Any], tuple[int | None, int, str, float | None]] | None:
        needle = label_substring.strip().lower()
        if not needle:
            return None
        for feature in self._iter_feature_params():
            options = self._extract_feature_options(feature)
            for option in options:
                _, _, label, _ = option
                if needle in label.strip().lower():
                    return feature, option
        return None

    def _list_feature_names(self) -> list[str]:
        names: list[str] = []
        for feature in self._iter_feature_params():
            name = feature.get("name")
            if isinstance(name, str):
                names.append(name)
        return names

    async def _get_filter_options(self) -> list[FilterOption]:
        if self._filter_options is not None:
            return self._filter_options
        if self.simulation:
            self._filter_options = [
                FilterOption(
                    parameter={},
                    mode_index=0,
                    index=i,
                    label=_canonical_filter_label(label, i),
                )
                for i, label in enumerate(FALLBACK_FILTER_LABELS)
            ]
            return self._filter_options
        payload = await self._ensure_params_config()
        if payload is None:
            if self._filter_options:
                return self._filter_options
            self._filter_options = [
                FilterOption(
                    parameter=None,
                    mode_index=0,
                    index=i,
                    label=_canonical_filter_label(label, i),
                    controllable=False,
                )
                for i, label in enumerate(FALLBACK_FILTER_LABELS)
            ]
            logger.info(
                "dwarf.camera.filter_options_fallback",
                filters=FALLBACK_FILTER_LABELS,
                reason="params_config_unavailable",
            )
            return self._filter_options

        options: list[FilterOption] = []
        seen: set[str] = set()

        def _add_option(
            parameter: dict[str, Any] | None,
            mode_index: int | None,
            index: int,
            label: str,
            continue_value: float | None,
        ) -> None:
            resolved = _canonical_filter_label(label, index)
            key = resolved.strip().lower()
            if key in seen:
                return
            seen.add(key)
            param_dict: dict[str, Any] | None = parameter if isinstance(parameter, dict) else None
            has_id = False
            if param_dict is not None:
                try:
                    _ = param_dict.get("id")
                    has_id = _ is not None
                except AttributeError:
                    param_dict = None
            options.append(
                FilterOption(
                    parameter=param_dict,
                    mode_index=mode_index if mode_index is not None else 0,
                    index=index,
                    label=resolved,
                    continue_value=continue_value,
                    controllable=has_id,
                )
            )

        filter_keywords = ("filter", "ir cut", "ir-cut")
        for _, param in self._iter_camera_support_params(camera_name="tele"):
            name = str(param.get("name", "")).strip().lower()
            if not any(keyword in name for keyword in filter_keywords):
                continue
            for mode_index, index, label, continue_value in self._extract_support_param_options(param):
                _add_option(param, mode_index, index, label, continue_value)

        if not options:
            for feature in self._iter_feature_params():
                feature_name = str(feature.get("name", "")).strip().lower()
                if "filter" not in feature_name:
                    continue
                for mode_index, index, label, continue_value in self._extract_feature_options(feature):
                    _add_option(feature, mode_index, index, label, continue_value)

        if not options:
            fallback = self._find_feature_option_by_label("filter")
            if fallback is not None:
                feature, option = fallback
                mode_index, index, label, continue_value = option
                _add_option(feature, mode_index, index, label, continue_value)

        if not options:
            self._filter_options = [
                FilterOption(
                    parameter=None,
                    mode_index=0,
                    index=i,
                    label=_canonical_filter_label(label, i),
                    controllable=False,
                )
                for i, label in enumerate(FALLBACK_FILTER_LABELS)
            ]
            logger.info(
                "dwarf.camera.filter_options_fallback",
                filters=FALLBACK_FILTER_LABELS,
                reason="params_config_missing_filters",
            )
        else:
            self._filter_options = options
        return self._filter_options

    async def get_filter_labels(self) -> list[str]:
        options = await self._get_filter_options()
        return [option.label for option in options]

    def get_filter_position(self) -> int | None:
        return self.camera_state.filter_index

    async def _apply_filter_option(self, position: int, option: FilterOption) -> None:
        state = self.camera_state
        if self.simulation:
            state.filter_name = option.label
            state.filter_index = position
            logger.info(
                "dwarf.camera.filter_selected",
                filter=state.filter_name,
                position=position,
                mode_index=option.mode_index,
                index=option.index,
                continue_value=option.continue_value,
                simulated=True,
            )
            return

        if not option.controllable or not option.parameter:
            raise RuntimeError("filter_control_unavailable")

        param_id_raw = None
        try:
            param_id_raw = option.parameter.get("id")
            param_name = str(option.parameter.get("name", ""))
        except AttributeError:
            param_id_raw = None
            param_name = ""
        try:
            param_id = int(param_id_raw) if param_id_raw is not None else None
        except (TypeError, ValueError):
            param_id = None
        is_ir_cut = param_id == 8 or "ir cut" in param_name.strip().lower()

        if is_ir_cut:
            await self._set_ir_cut(value=option.index)
        else:
            await self._set_feature_param(
                option.parameter,
                mode_index=option.mode_index,
                index=option.index,
                continue_value=option.continue_value if option.continue_value is not None else 0.0,
            )
        state.filter_name = option.label
        state.filter_index = position
        logger.info(
            "dwarf.camera.filter_selected",
            filter=state.filter_name,
            position=position,
            mode_index=option.mode_index,
            index=option.index,
            continue_value=option.continue_value,
        )

    async def _set_ir_cut(self, *, value: int) -> None:
        if self.simulation:
            return
        request = ReqSetIrCut()
        request.value = int(value)
        await self._send_and_check(
            protocol_pb2.ModuleId.MODULE_CAMERA_TELE,
            protocol_pb2.DwarfCMD.CMD_CAMERA_TELE_SET_IRCUT,
            request,
            expected_responses=self._tele_param_expected_responses(),
        )

    async def set_filter_position(self, position: int) -> str:
        options = await self._get_filter_options()
        if position < 0 or position >= len(options):
            raise ValueError("filter_position_out_of_range")
        option = options[position]
        state = self.camera_state
        if (
            state.filter_index == position
            and state.filter_name
            and state.filter_name.strip().lower() == option.label.lower()
        ):
            return state.filter_name
        if not self.simulation:
            await self._ensure_ws()
        await self._apply_filter_option(position, option)
        return option.label

    async def _ensure_default_filter(self, default_filter: str = "VIS") -> None:
        state = self.camera_state
        target = default_filter.strip()
        if not target:
            return
        options = await self._get_filter_options()
        if not options:
            logger.warning(
                "dwarf.camera.filter_feature_missing",
                filter=target,
                available=self._list_feature_names(),
            )
            return

        target_lower = target.lower()
        if state.filter_name:
            current_lower = state.filter_name.strip().lower()
            if target_lower in current_lower:
                if state.filter_index is None:
                    for idx, option in enumerate(options):
                        if option.label.lower() == current_lower:
                            state.filter_index = idx
                            break
                return

        selected_index: int | None = None
        for idx, option in enumerate(options):
            if option.label.lower() == target_lower:
                selected_index = idx
                break
        if selected_index is None:
            for idx, option in enumerate(options):
                if target_lower in option.label.lower():
                    selected_index = idx
                    break
        if selected_index is None:
            logger.warning(
                "dwarf.camera.filter_default_missing",
                filter=target,
                available=[option.label for option in options],
            )
            selected_index = 0

        option = options[selected_index]
        try:
            await self.set_filter_position(selected_index)
        except Exception as exc:  # pragma: no cover - hardware dependent
            logger.warning(
                "dwarf.camera.filter_default_apply_failed",
                filter=target,
                position=selected_index,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            if option.controllable and option.parameter:
                try:
                    await self._apply_filter_option(selected_index, option)
                except Exception as inner_exc:  # pragma: no cover - defensive fallback
                    logger.warning(
                        "dwarf.camera.filter_default_apply_failed_fallback",
                        filter=target,
                        position=selected_index,
                        error=str(inner_exc),
                        error_type=type(inner_exc).__name__,
                    )

    async def _ensure_selected_filter(self) -> None:
        state = self.camera_state
        index = state.filter_index
        if index is None:
            await self._ensure_default_filter()
            return

        options = await self._get_filter_options()
        if not options:
            await self._ensure_default_filter()
            return

        if index < 0 or index >= len(options):
            logger.warning(
                "dwarf.camera.filter_index_out_of_range",
                index=index,
                total_options=len(options),
            )
            state.filter_index = None
            state.filter_name = ""
            await self._ensure_default_filter()
            return

        option = options[index]
        if not option.controllable:
            if not state.filter_name:
                state.filter_name = option.label
            return

        current_label = (state.filter_name or "").strip().lower()
        desired_label = option.label.strip().lower()
        if current_label == desired_label and state.filter_name:
            return

        try:
            await self._apply_filter_option(index, option)
        except Exception as exc:  # pragma: no cover - hardware dependent
            logger.warning(
                "dwarf.camera.filter_refresh_failed",
                position=index,
                filter=option.label,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            if current_label:
                return
            state.filter_index = None
            state.filter_name = ""
            await self._ensure_default_filter()

    async def _set_feature_param(
        self,
        feature: dict[str, Any],
        *,
        mode_index: int,
        index: int = 0,
        continue_value: float = 0.0,
    ) -> None:
        if self.simulation:
            return
        request = ReqSetFeatureParams()
        param = CommonParam()
        feature_id = feature.get("id")
        param.hasAuto = bool(feature.get("hasAuto", False))
        param.auto_mode = int(feature.get("autoMode", 0))
        param.id = int(feature_id or 0)
        param.mode_index = mode_index
        param.index = index
        param.continue_value = float(continue_value)
        request.param.CopyFrom(param)
        try:
            await self._send_and_check(
                protocol_pb2.ModuleId.MODULE_CAMERA_TELE,
                protocol_pb2.DwarfCMD.CMD_CAMERA_TELE_SET_FEATURE_PARAM,
                request,
                expected_responses=self._tele_param_expected_responses(),
            )
        except Exception as exc:  # pragma: no cover - hardware dependent
            logger.warning(
                "dwarf.camera.feature_param_set_failed",
                feature_id=feature_id,
                mode_index=mode_index,
                index=index,
                continue_value=continue_value,
                error=str(exc),
            )

    async def _configure_astro_capture(
        self,
        *,
        frames: int = 1,
        binning: tuple[int, int] | None = None,
    ) -> None:
        if self.simulation:
            return
        config = await self._ensure_params_config()
        if config is None:
            return
        bin_x, bin_y = (binning or (1, 1))
        try:
            bin_x = max(1, int(bin_x))
            bin_y = max(1, int(bin_y))
        except (TypeError, ValueError):
            bin_x, bin_y = (1, 1)

        async def _set_feature_by_label(feature_name: str, label_tokens: tuple[str, ...]) -> None:
            feature = self._find_feature_param(feature_name)
            if feature is None:
                logger.warning("dwarf.camera.feature_param_missing", name=feature_name)
                return
            options = self._extract_feature_options(feature)
            for mode_index, index, label, continue_value in options:
                lowered = label.strip().lower()
                if all(token in lowered for token in label_tokens):
                    await self._set_feature_param(
                        feature,
                        mode_index=mode_index or 0,
                        index=index,
                        continue_value=continue_value or 0.0,
                    )
                    return
            logger.warning(
                "dwarf.camera.feature_option_missing",
                feature=feature_name,
                label_tokens=label_tokens,
            )

        desired_fixed = (
            ("Astro display source", 0, 1, 0.0),
            ("Astro ai enhance", 0, 0, 0.0),
        )
        for name, mode_index, index, continue_value in desired_fixed:
            feature = self._find_feature_param(name)
            if feature is None:
                logger.warning("dwarf.camera.feature_param_missing", name=name)
                continue
            await self._set_feature_param(
                feature,
                mode_index=mode_index,
                index=index,
                continue_value=continue_value,
            )

        bin_label = f"{bin_x}x{bin_y}"
        await _set_feature_by_label("Astro binning", (bin_label.lower(),))
        await _set_feature_by_label("Astro format", ("fit",))

        frames = max(1, int(frames))
        frames_feature = self._find_feature_param("Astro img_to_take")
        if frames_feature is not None:
            await self._set_feature_param(
                frames_feature,
                mode_index=1,
                index=0,
                continue_value=float(frames),
            )
        else:
            logger.warning("dwarf.camera.feature_param_missing", name="Astro img_to_take")

    async def _start_astro_capture(self, *, timeout: float) -> int:
        if self.simulation:
            return protocol_pb2.OK
        request = astro_pb2.ReqCaptureRawLiveStacking()
        response = await self._send_command(
            protocol_pb2.ModuleId.MODULE_ASTRO,
            protocol_pb2.DwarfCMD.CMD_ASTRO_START_CAPTURE_RAW_LIVE_STACKING,
            request,
            timeout=timeout,
        )
        code = getattr(response, "code", protocol_pb2.OK)
        if code == protocol_pb2.OK:
            return code
        if code == protocol_pb2.CODE_ASTRO_NEED_GOTO:
            logger.warning(
                "dwarf.camera.astro_capture_goto_ignored",
                module_id=protocol_pb2.ModuleId.MODULE_ASTRO,
                command_id=protocol_pb2.DwarfCMD.CMD_ASTRO_START_CAPTURE_RAW_LIVE_STACKING,
                code=code,
            )
            return code
        if code == protocol_pb2.CODE_ASTRO_FUNCTION_BUSY:
            logger.warning(
                "dwarf.camera.astro_capture_busy",
                module_id=protocol_pb2.ModuleId.MODULE_ASTRO,
                command_id=protocol_pb2.DwarfCMD.CMD_ASTRO_START_CAPTURE_RAW_LIVE_STACKING,
                code=code,
            )
        else:
            logger.warning(
                "dwarf.camera.astro_capture_unexpected_code",
                module_id=protocol_pb2.ModuleId.MODULE_ASTRO,
                command_id=protocol_pb2.DwarfCMD.CMD_ASTRO_START_CAPTURE_RAW_LIVE_STACKING,
                code=code,
            )
        raise DwarfCommandError(
            protocol_pb2.ModuleId.MODULE_ASTRO,
            protocol_pb2.DwarfCMD.CMD_ASTRO_START_CAPTURE_RAW_LIVE_STACKING,
            code,
        )

    async def _astro_go_live(self) -> None:
        if self.simulation:
            return
        request = astro_pb2.ReqGoLive()
        try:
            await self._send_and_check(
                protocol_pb2.ModuleId.MODULE_ASTRO,
                protocol_pb2.DwarfCMD.CMD_ASTRO_GO_LIVE,
                request,
                timeout=max(self.settings.go_live_timeout_seconds, 1.0),
            )
        except DwarfCommandError as exc:
            logger.warning(
                "dwarf.camera.go_live_failed",
                module_id=exc.module_id,
                command_id=exc.command_id,
                error_code=exc.code,
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning(
                "dwarf.camera.go_live_error",
                error=str(exc),
                error_type=type(exc).__name__,
            )

    async def _check_dark_library(self) -> tuple[int | None, int | None]:
        if self.simulation:
            return protocol_pb2.OK, None
        request = astro_pb2.ReqCheckDarkFrame()
        timeout = max(self.settings.dark_check_timeout_seconds, 1.0)
        try:
            response = await self._send_request(
                protocol_pb2.ModuleId.MODULE_ASTRO,
                protocol_pb2.DwarfCMD.CMD_ASTRO_CHECK_GOT_DARK,
                request,
                astro_pb2.ResCheckDarkFrame,
                timeout=timeout,
            )
        except Exception as exc:  # pragma: no cover - hardware dependent
            logger.warning(
                "dwarf.camera.dark_check_failed",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return None, None
        code = getattr(response, "code", None)
        progress = getattr(response, "progress", None)
        return code, progress

    async def _ensure_dark_library(self, *, continue_without_darks: bool) -> bool:
        code, progress = await self._check_dark_library()
        state = self.camera_state
        previous_code = self._last_dark_check_code
        if code is not None:
            self._last_dark_check_code = code
            state.last_dark_check_code = code
        if code is None:
            logger.warning(
                "dwarf.camera.dark_library_unknown",
                reason="no_response",
                continue_without_darks=continue_without_darks,
            )
            return continue_without_darks
        if code == protocol_pb2.OK:
            if previous_code != code:
                logger.info("dwarf.camera.dark_library_ready")
            if state.last_error == "dark_missing":
                state.last_error = None
            return True
        if code == protocol_pb2.CODE_ASTRO_DARK_NOT_FOUND:
            if previous_code != code:
                logger.warning(
                    "dwarf.camera.dark_library_missing",
                    progress=progress,
                    continue_without_darks=continue_without_darks,
                )
            if continue_without_darks:
                state.last_error = "dark_missing"
                return False
            raise DwarfCommandError(
                protocol_pb2.ModuleId.MODULE_ASTRO,
                protocol_pb2.DwarfCMD.CMD_ASTRO_CHECK_GOT_DARK,
                code,
            )
        logger.warning(
            "dwarf.camera.dark_library_unexpected_code",
            code=code,
            progress=progress,
            continue_without_darks=continue_without_darks,
        )
        if continue_without_darks:
            state.last_error = f"dark_code:{code}"
            return False
        raise DwarfCommandError(
            protocol_pb2.ModuleId.MODULE_ASTRO,
            protocol_pb2.DwarfCMD.CMD_ASTRO_CHECK_GOT_DARK,
            code,
        )

    async def _start_photo_capture(self, *, timeout: float) -> None:
        if self.simulation:
            return
        request = ReqPhotoRaw()
        try:
            await self._send_and_check(
                protocol_pb2.ModuleId.MODULE_CAMERA_TELE,
                protocol_pb2.DwarfCMD.CMD_CAMERA_TELE_PHOTO_RAW,
                request,
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "dwarf.camera.photo_raw_timeout",
                timeout=timeout,
            )

    async def _stop_astro_capture(self) -> None:
        if self.simulation:
            return
        try:
            request = astro_pb2.ReqStopCaptureRawLiveStacking()
            await self._send_and_check(
                protocol_pb2.ModuleId.MODULE_ASTRO,
                protocol_pb2.DwarfCMD.CMD_ASTRO_STOP_CAPTURE_RAW_LIVE_STACKING,
                request,
            )
        except Exception as exc:  # pragma: no cover - hardware dependent
            logger.debug("dwarf.astro.stop_capture_failed", error=str(exc))

    async def _set_exposure_mode_manual(self) -> None:
        request = ReqSetExpMode()
        request.mode = protocol_pb2.PhotoMode.Manual
        await self._send_and_check(
            protocol_pb2.ModuleId.MODULE_CAMERA_TELE,
            protocol_pb2.DwarfCMD.CMD_CAMERA_TELE_SET_EXP_MODE,
            request,
            expected_responses=self._tele_param_expected_responses(),
        )

    async def _set_exposure_index(self, index: int) -> None:
        request = ReqSetExp()
        request.index = index
        await self._send_and_check(
            protocol_pb2.ModuleId.MODULE_CAMERA_TELE,
            protocol_pb2.DwarfCMD.CMD_CAMERA_TELE_SET_EXP,
            request,
            expected_responses=self._tele_param_expected_responses(),
        )

    async def _ensure_gain_settings(self) -> None:
        if self.simulation:
            return
        state = self.camera_state
        gain_value = state.requested_gain
        if gain_value is None:
            return
        try:
            gain_index = int(round(gain_value))
        except (TypeError, ValueError):
            return
        gain_index = max(0, min(gain_index, 255))
        if state.applied_gain_index == gain_index:
            return
        try:
            await self._set_gain_mode_manual()
        except Exception as exc:  # pragma: no cover - hardware dependent
            logger.debug(
                "dwarf.camera.gain_mode_set_failed",
                requested_gain=gain_index,
                error=str(exc),
                error_type=type(exc).__name__,
            )
        try:
            await self._set_gain_index(gain_index)
        except DwarfCommandError as exc:  # pragma: no cover - hardware dependent
            logger.warning(
                "dwarf.camera.gain_set_failed",
                requested_gain=gain_index,
                error_code=exc.code,
                module_id=exc.module_id,
                command_id=exc.command_id,
            )
            return
        except Exception as exc:  # pragma: no cover - hardware dependent
            logger.warning(
                "dwarf.camera.gain_set_error",
                requested_gain=gain_index,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return
        state.applied_gain_index = gain_index
        logger.info("dwarf.camera.gain_applied", gain=gain_index)

    async def _set_gain_mode_manual(self) -> None:
        request = ReqSetGainMode()
        request.mode = 1
        await self._send_and_check(
            protocol_pb2.ModuleId.MODULE_CAMERA_TELE,
            protocol_pb2.DwarfCMD.CMD_CAMERA_TELE_SET_GAIN_MODE,
            request,
            expected_responses=self._tele_param_expected_responses(),
        )

    async def _set_gain_index(self, index: int) -> None:
        request = ReqSetGain()
        request.index = index
        await self._send_and_check(
            protocol_pb2.ModuleId.MODULE_CAMERA_TELE,
            protocol_pb2.DwarfCMD.CMD_CAMERA_TELE_SET_GAIN,
            request,
            expected_responses=self._tele_param_expected_responses(),
        )

    async def _refresh_capture_baseline(self, *, capture_kind: str) -> None:
        await self._refresh_ftp_baseline(capture_kind=capture_kind)
        if capture_kind == "photo":
            await self._refresh_album_baseline()
        else:
            state = self.camera_state
            state.pending_album_baseline = state.last_album_mod_time

    async def _refresh_ftp_baseline(self, *, capture_kind: str) -> None:
        state = self.camera_state
        if self.simulation:
            state.pending_ftp_baseline = state.last_ftp_entry
            return
        try:
            latest = await self._ftp_client.get_latest_photo_entry(
                capture_kind=capture_kind,
            )
        except Exception as exc:  # pragma: no cover - hardware dependent
            logger.warning("dwarf.camera.ftp_baseline_failed", error=str(exc))
            state.pending_ftp_baseline = state.last_ftp_entry
            return
        if latest is not None:
            state.last_ftp_entry = latest
        state.pending_ftp_baseline = state.last_ftp_entry

    async def _refresh_album_baseline(self) -> None:
        state = self.camera_state
        if self.simulation:
            state.pending_album_baseline = state.last_album_mod_time
            return
        mod_time, entry = await self._get_latest_album_entry()
        if mod_time is not None:
            state.last_album_mod_time = mod_time
        if entry is not None:
            state.last_album_file = self._album_entry_file(entry)
        state.pending_album_baseline = state.last_album_mod_time

    async def _get_latest_album_entry(
        self,
        *,
        media_type: int = 1,
    ) -> tuple[int | None, dict[str, Any] | None]:
        try:
            entries = await self._http_client.list_album_media_infos(media_type=media_type, page_size=1)
        except Exception as exc:  # pragma: no cover - hardware dependent
            logger.warning("dwarf.camera.album_list_failed", error=str(exc))
            return None, None
        if not entries:
            return None, None
        entry = entries[0]
        mod_time_raw = entry.get("modificationTime")
        try:
            mod_time = int(mod_time_raw)
        except (TypeError, ValueError):
            mod_time = None
        return mod_time, entry

    @staticmethod
    def _album_entry_file(entry: dict[str, Any]) -> str | None:
        file_path = entry.get("filePath")
        if isinstance(file_path, str) and file_path:
            return file_path
        file_name = entry.get("fileName")
        if isinstance(file_name, str) and file_name:
            return file_name
        return None

    async def _simulate_capture(self, state: CameraState) -> None:
        await asyncio.sleep(state.duration)
        width = 640
        height = 480
        x = np.linspace(0, 65535, width, dtype=np.uint16)
        y = np.linspace(0, 65535, height, dtype=np.uint16)
        grid = np.outer(y, np.ones_like(x)).astype(np.uint16)
        state.image = grid
        state.frame_width = width
        state.frame_height = height
        state.image_timestamp = time.time()
        state.last_end_time = state.image_timestamp
        state.start_time = None

    async def _fetch_capture(self, state: CameraState) -> None:
        await asyncio.sleep(max(state.duration, 0.1))
        astro_mode = state.capture_mode == "astro"
        image_captured = state.image is not None
        if not self.simulation:
            ftp_success = False
            try:
                ftp_success = await self._attempt_ftp_capture(state)
            finally:
                if astro_mode:
                    await self._stop_astro_capture()
            if ftp_success:
                image_captured = True
            else:
                if not astro_mode or state.image is None:
                    await self._attempt_album_capture(state)
                image_captured = state.image is not None
        else:
            if not astro_mode or state.image is None:
                await self._attempt_album_capture(state)
            image_captured = state.image is not None

        if astro_mode and image_captured:
            await self._astro_go_live()

    async def _attempt_ftp_capture(self, state: CameraState) -> bool:
        baseline = state.pending_ftp_baseline
        timeout = max(state.duration + 25.0, 30.0)
        try:
            capture = await self._ftp_client.wait_for_new_photo(
                baseline,
                timeout=timeout,
                capture_kind=state.capture_mode,
            )
        except Exception as exc:  # pragma: no cover - hardware dependent
            logger.warning(
                "dwarf.camera.ftp_capture_failed",
                duration=state.duration,
                error=str(exc),
            )
            capture = None
        if capture is None:
            baseline_path = baseline.path if baseline else None
            logger.warning(
                "dwarf.camera.ftp_timeout",
                duration=state.duration,
                baseline=baseline_path,
            )
            state.start_time = None
            state.last_error = "ftp_timeout"
            state.last_end_time = time.time()
            state.pending_ftp_baseline = state.last_ftp_entry
            return False
        try:
            frame = self._decode_capture_content(capture.entry.path, capture.content)
        except Exception as exc:
            logger.warning(
                "dwarf.camera.ftp_decode_failed",
                path=capture.entry.path,
                error=str(exc),
            )
            state.start_time = None
            state.last_error = "ftp_decode_failed"
            state.last_end_time = time.time()
            state.pending_ftp_baseline = capture.entry
            return False
        timestamp = capture.entry.timestamp or time.time()
        self._store_frame(state, frame, timestamp)
        state.last_ftp_entry = capture.entry
        state.pending_ftp_baseline = capture.entry
        return True

    async def _attempt_album_capture(self, state: CameraState) -> None:
        if self.simulation:
            return
        baseline = state.pending_album_baseline
        last_known_file = state.last_album_file
        deadline = time.time() + max(state.duration + 15.0, 20.0)
        entry: dict[str, Any] | None = None
        media_type = 4 if state.capture_mode == "astro" else 1
        while time.time() < deadline:
            mod_time, latest_entry = await self._get_latest_album_entry(media_type=media_type)
            if latest_entry is None:
                await asyncio.sleep(0.75)
                continue
            file_id = self._album_entry_file(latest_entry)
            is_new = False
            if mod_time is not None:
                if baseline is None or mod_time > baseline:
                    is_new = True
            if not is_new and file_id and file_id != last_known_file:
                is_new = True
            if is_new:
                entry = latest_entry
                if mod_time is not None:
                    state.last_album_mod_time = mod_time
                if file_id:
                    state.last_album_file = file_id
                break
            await asyncio.sleep(0.75)

        if entry is None:
            logger.warning(
                "dwarf.camera.album_capture_timeout",
                duration=state.duration,
                baseline=baseline,
                last_known_file=last_known_file,
            )
            state.start_time = None
            state.last_error = "album_timeout"
            state.pending_album_baseline = state.last_album_mod_time
            state.last_end_time = time.time()
            return

        file_id = self._album_entry_file(entry)
        if not file_id:
            logger.warning("dwarf.camera.album_entry_missing_file", entry=entry)
            state.start_time = None
            state.last_error = "album_missing_file"
            state.pending_album_baseline = state.last_album_mod_time
            state.last_end_time = time.time()
            return

        try:
            media_bytes = await self._http_client.fetch_media_file(file_id)
        except Exception as exc:  # pragma: no cover - hardware dependent
            logger.warning(
                "dwarf.camera.album_download_failed",
                path=file_id,
                error=str(exc),
            )
            state.start_time = None
            state.last_error = "album_download_failed"
            state.pending_album_baseline = state.last_album_mod_time
            state.last_end_time = time.time()
            return

        try:
            frame = self._decode_capture_content(file_id, media_bytes)
        except Exception as exc:
            logger.warning("dwarf.camera.decode_failed", path=file_id, error=str(exc))
            state.start_time = None
            state.last_error = "decode_failed"
            state.pending_album_baseline = state.last_album_mod_time
            state.last_end_time = time.time()
            return

        mod_time_raw = entry.get("modificationTime")
        try:
            timestamp = float(mod_time_raw)
        except (TypeError, ValueError):
            timestamp = time.time()
        self._store_frame(state, frame, timestamp)
        state.pending_album_baseline = state.last_album_mod_time

    def _store_frame(self, state: CameraState, frame: np.ndarray, timestamp: float) -> None:
        if frame.dtype != np.uint16:
            frame = frame.astype(np.uint16, copy=False)
        state.image = frame
        state.frame_height, state.frame_width = frame.shape[:2]
        state.image_timestamp = timestamp
        state.last_end_time = timestamp
        state.start_time = None
        state.last_error = None

    def _decode_capture_content(self, identifier: str, content: bytes) -> np.ndarray:
        name = identifier.rsplit("/", 1)[-1]
        lower = name.lower()
        if lower.endswith((".fits", ".fit")):
            return self._decode_fits(content)
        return self._decode_jpeg(content)

    @staticmethod
    def _decode_jpeg(content: bytes) -> np.ndarray:
        import cv2  # type: ignore

        array = np.frombuffer(content, dtype=np.uint8)
        frame = cv2.imdecode(array, cv2.IMREAD_UNCHANGED)
        if frame is None:
            raise ValueError("decode_failed")
        if frame.ndim == 3:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if frame.dtype == np.uint8:
            frame = (frame.astype(np.uint16, copy=False) << 8)
        elif frame.dtype != np.uint16:
            frame = frame.astype(np.uint16, copy=False)
        return frame

    @staticmethod
    def _decode_fits(content: bytes) -> np.ndarray:
        header: dict[str, Any] = {}
        offset = 0
        block_size = 2880
        content_len = len(content)
        while True:
            if offset + 80 > content_len:
                raise ValueError("fits_header_incomplete")
            card = content[offset : offset + 80]
            offset += 80
            keyword = card[0:8].decode("ascii", errors="ignore").strip()
            if keyword == "END":
                break
            if not keyword:
                continue
            value_field = card[10:80].decode("ascii", errors="ignore")
            value_str = value_field.split("/", 1)[0].strip()
            if value_str:
                header[keyword] = DwarfSession._parse_fits_value(value_str)
        header_size = ((offset + block_size - 1) // block_size) * block_size
        bitpix = int(header.get("BITPIX", 16))
        naxis = int(header.get("NAXIS", 0))
        if naxis < 2:
            raise ValueError("fits_naxis")
        width = int(header.get("NAXIS1", 0))
        height = int(header.get("NAXIS2", 0))
        if width <= 0 or height <= 0:
            raise ValueError("fits_dimensions")
        dtype = DwarfSession._fits_dtype(bitpix)
        if dtype is None:
            raise ValueError(f"fits_bitpix_{bitpix}")
        expected = width * height
        data_section = content[header_size:]
        array = np.frombuffer(data_section, dtype=dtype, count=expected)
        if array.size < expected:
            raise ValueError("fits_data_short")
        array = array.reshape((height, width))
        bscale = float(header.get("BSCALE", 1.0))
        bzero = float(header.get("BZERO", 0.0))
        scaled = array.astype(np.float64) * bscale + bzero
        scaled = np.clip(scaled, 0, 65535)
        return scaled.astype(np.uint16)

    @staticmethod
    def _parse_fits_value(value: str) -> Any:
        stripped = value.strip()
        if not stripped:
            return None
        if stripped.startswith("'") and stripped.endswith("'"):
            return stripped.strip("'")
        upper = stripped.upper()
        if upper in {"T", "F"}:
            return upper == "T"
        try:
            if any(ch in stripped for ch in (".", "E", "e")):
                return float(stripped)
            return int(stripped)
        except ValueError:
            return stripped

    @staticmethod
    def _fits_dtype(bitpix: int) -> np.dtype[Any] | None:
        if bitpix == 8:
            return np.dtype(np.uint8)
        if bitpix == 16:
            return np.dtype(">i2")
        if bitpix == 32:
            return np.dtype(">i4")
        if bitpix == 64:
            return np.dtype(">i8")
        if bitpix == -32:
            return np.dtype(">f4")
        if bitpix == -64:
            return np.dtype(">f8")
        return None

    # --- Focuser -------------------------------------------------------------------

    async def focuser_connect(self) -> None:
        state = self.focuser_state
        if state.connected:
            return
        state.connected = True
        state.is_moving = False
        if self.simulation:
            return
        await self._ensure_ws()

    async def focuser_disconnect(self) -> None:
        state = self.focuser_state
        if not state.connected:
            return
        if not self.simulation:
            await self._ensure_ws()
            stop = ReqStopManualContinuFocus()
            with contextlib.suppress(Exception):
                await self._send_and_check(
                    protocol_pb2.ModuleId.MODULE_FOCUS,
                    protocol_pb2.DwarfCMD.CMD_FOCUS_STOP_MANUAL_CONTINU_FOCUS,
                    stop,
                )
        state.connected = False
        state.is_moving = False

    async def focuser_move(self, delta: int, *, target: int | None = None) -> None:
        state = self.focuser_state
        state.is_moving = True
        start_position = state.position
        desired_target = start_position + delta if target is None else target
        target = max(0, min(desired_target, 20000))
        delta = target - start_position
        if delta == 0:
            state.is_moving = False
            return

        direction = 1 if delta > 0 else -1
        steps = abs(delta)

        if self.simulation:
            await self._simulate_focus_move(delta)
            state.position = target
            state.last_update = time.time()
            state.is_moving = False
            return

        await self._ensure_ws()
        received_update = False
        try:
            last_update_age = None if state.last_update is None else time.time() - state.last_update
            prefer_single_step = steps <= 10
            fallback_reason = None
            if steps > 10 and (last_update_age is None or last_update_age > 5.0):
                fallback_reason = "stale_focus_telemetry" if last_update_age is not None else "no_focus_telemetry"
            logger.info(
                "dwarf.focus.move.dispatch",
                start=start_position,
                target=target,
                delta=delta,
                steps=steps,
                prefer_single_step=prefer_single_step,
                last_update_age=last_update_age,
                fallback_reason=fallback_reason,
            )
            if prefer_single_step:
                request = ReqManualSingleStepFocus()
                request.direction = 1 if direction > 0 else 0
                for _ in range(steps):
                    self._focus_update_event.clear()
                    await self._send_and_check(
                        protocol_pb2.ModuleId.MODULE_FOCUS,
                        protocol_pb2.DwarfCMD.CMD_FOCUS_MANUAL_SINGLE_STEP_FOCUS,
                        request,
                    )
                    try:
                        await asyncio.wait_for(self._focus_update_event.wait(), timeout=0.8)
                        received_update = True
                    except asyncio.TimeoutError:
                        state.position = max(0, min(state.position + direction, 20000))
                        state.last_update = time.time()
                        received_update = True
                    finally:
                        self._focus_update_event.clear()
                    current = state.position
                    if direction > 0 and current >= target:
                        break
                    if direction < 0 and current <= target:
                        break
                    await asyncio.sleep(0.02)
            else:
                start_request = ReqManualContinuFocus()
                start_request.direction = 1 if direction > 0 else 0
                self._focus_update_event.clear()
                await self._send_and_check(
                    protocol_pb2.ModuleId.MODULE_FOCUS,
                    protocol_pb2.DwarfCMD.CMD_FOCUS_START_MANUAL_CONTINU_FOCUS,
                    start_request,
                )
                deadline = time.monotonic() + min(max(steps * 0.015, 1.5), 15.0)
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    timeout = min(0.8, max(0.05, remaining))
                    try:
                        await asyncio.wait_for(self._focus_update_event.wait(), timeout=timeout)
                    except asyncio.TimeoutError:
                        timed_out = True
                    else:
                        timed_out = False
                        received_update = True
                    finally:
                        self._focus_update_event.clear()
                    if timed_out:
                        continue
                    position = self.focuser_state.position
                    if direction > 0 and position >= target:
                        break
                    if direction < 0 and position <= target:
                        break

                stop_request = ReqStopManualContinuFocus()
                self._focus_update_event.clear()
                await self._send_and_check(
                    protocol_pb2.ModuleId.MODULE_FOCUS,
                    protocol_pb2.DwarfCMD.CMD_FOCUS_STOP_MANUAL_CONTINU_FOCUS,
                    stop_request,
                )
                try:
                    await asyncio.wait_for(self._focus_update_event.wait(), timeout=0.8)
                    received_update = True
                except asyncio.TimeoutError:
                    pass
                finally:
                    self._focus_update_event.clear()
        except Exception:
            state.is_moving = False
            raise
        else:
            if not received_update:
                state.position = target
                state.last_update = time.time()
            state.position = max(0, min(state.position, 20000))
            state.is_moving = False
            logger.info(
                "dwarf.focus.move.completed",
                position=state.position,
                received_update=received_update,
            )

    async def focuser_halt(self) -> None:
        state = self.focuser_state
        if self.simulation:
            state.is_moving = False
            return
        await self._ensure_ws()
        stop = ReqStopManualContinuFocus()
        try:
            await self._send_and_check(
                protocol_pb2.ModuleId.MODULE_FOCUS,
                protocol_pb2.DwarfCMD.CMD_FOCUS_STOP_MANUAL_CONTINU_FOCUS,
                stop,
            )
        finally:
            state.is_moving = False

    async def _simulate_focus_move(self, delta: int) -> None:
        steps = abs(delta)
        direction = 1 if delta > 0 else -1
        for _ in range(steps):
            self.focuser_state.position += direction
            self.focuser_state.position = max(0, min(self.focuser_state.position, 20000))
            self.focuser_state.last_update = time.time()
            self._focus_update_event.set()
            await asyncio.sleep(0.005)


_session: DwarfSession | None = None
_session_lock = asyncio.Lock()
_session_settings: Settings | None = None


def configure_session(settings: Settings) -> None:
    global _session_settings, _session
    _session_settings = settings
    if _session is not None:
        _session.settings = settings
        _session.simulation = settings.force_simulation
        _session._ws_client.set_client_id(settings.dwarf_ws_client_id)
        _session._ws_client.uri = f"ws://{settings.dwarf_ap_ip}:{settings.dwarf_ws_port}/"
        _session._http_client.host = settings.dwarf_ap_ip
        _session._http_client.api_port = settings.dwarf_http_port
        _session._http_client.jpeg_port = settings.dwarf_jpeg_port
        _session._http_client.timeout = settings.http_timeout_seconds
        _session._http_client.retries = settings.http_retries
        _session._http_client._client = None
        _session._http_client._jpeg_client = None
        _session._ftp_client.host = settings.dwarf_ap_ip
        _session._ftp_client.port = settings.dwarf_ftp_port
        _session._ftp_client.timeout = settings.ftp_timeout_seconds
        _session._ftp_client.poll_interval = settings.ftp_poll_interval_seconds
        _session._ws_bootstrapped = False
        _session._params_config = None
        _session._filter_options = None


async def get_session() -> DwarfSession:
    global _session
    if _session is None:
        async with _session_lock:
            if _session is None:
                settings = _session_settings or Settings()
                _session = DwarfSession(settings)
    return _session


async def shutdown_session() -> None:
    global _session
    if _session is None:
        return
    await _session.shutdown()
