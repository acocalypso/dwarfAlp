from __future__ import annotations

import asyncio
import contextlib
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np
import structlog

from ..config.settings import Settings
from ..proto import protocol_pb2
from . import exposure
from ..proto.dwarf_messages import (
    CommonParam,
    ComResponse,
    ReqAstroStartCaptureRawLiveStacking,
    ReqAstroStopCaptureRawLiveStacking,
    ReqCloseCamera,
    ReqGetSystemWorkingState,
    ReqGotoDSO,
    ReqManualContinuFocus,
    ReqManualSingleStepFocus,
    ReqPhotoRaw,
    ReqOpenCamera,
    ReqSetFeatureParams,
    ReqSetExp,
    ReqSetExpMode,
    ReqStopGoto,
    ReqStopManualContinuFocus,
    ReqsetMasterLock,
    ResNotifyHostSlaveMode,
)
from .ftp_client import DwarfFtpClient, FtpPhotoEntry
from .http_client import DwarfHttpClient
from .ws_client import DwarfCommandError, DwarfWsClient, send_and_check

logger = structlog.get_logger(__name__)


@dataclass
class CameraState:
    connected: bool = False
    start_time: float | None = None
    duration: float = 0.0
    light: bool = True
    capture_mode: str = "photo"
    image: Optional[np.ndarray] = field(default=None, repr=False)
    capture_task: asyncio.Task[None] | None = field(default=None, repr=False)
    last_start_time: float | None = None
    last_end_time: float | None = None
    frame_width: int = 0
    frame_height: int = 0
    image_timestamp: float | None = None
    last_error: str | None = None
    last_album_mod_time: int | None = None
    last_album_file: str | None = None
    pending_album_baseline: int | None = None
    last_ftp_entry: "FtpPhotoEntry | None" = field(default=None, repr=False)
    pending_ftp_baseline: "FtpPhotoEntry | None" = field(default=None, repr=False)


@dataclass
class FocuserState:
    connected: bool = False
    position: int = 0
    is_moving: bool = False


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
        )
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
        self._refs: dict[str, int] = {"telescope": 0, "camera": 0, "focuser": 0}
        self._master_lock_acquired = False
        self._master_lock_lock = asyncio.Lock()
        self._lock = asyncio.Lock()
        self._ws_bootstrapped = False
        self.camera_state = CameraState()
        self.focuser_state = FocuserState()
        self._exposure_resolver: Optional[exposure.ExposureResolver] = None
        self._params_config: Optional[dict[str, Any]] = None

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
        await self._ensure_master_lock()

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
                response = await self._ws_client.send_command(
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

    # --- Telescope -----------------------------------------------------------------

    async def telescope_slew_to_coordinates(
        self,
        ra_hours: float,
        dec_degrees: float,
        *,
        target_name: str = "Custom",
    ) -> tuple[float, float]:
        if self.simulation:
            return ra_hours, dec_degrees

        await self._ensure_ws()
        request = ReqGotoDSO()
        request.ra = ra_hours * 15.0  # DWARF expects degrees
        request.dec = dec_degrees
        request.target_name = target_name
        await send_and_check(
            self._ws_client,
            protocol_pb2.ModuleId.MODULE_ASTRO,
            protocol_pb2.DwarfCMD.CMD_ASTRO_START_GOTO_DSO,
            request,
        )
        return ra_hours, dec_degrees

    async def telescope_abort_slew(self) -> None:
        if self.simulation:
            return
        await self._ensure_ws()
        request = ReqStopGoto()
        await send_and_check(
            self._ws_client,
            protocol_pb2.ModuleId.MODULE_ASTRO,
            protocol_pb2.DwarfCMD.CMD_ASTRO_STOP_GOTO,
            request,
        )

    # --- Camera --------------------------------------------------------------------

    async def camera_connect(self) -> None:
        self.camera_state.connected = True
        if self.simulation:
            return
        await self._ensure_ws()
        request = ReqOpenCamera()
        request.binning = False
        request.rtsp_encode_type = 0
        await send_and_check(
            self._ws_client,
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
        await send_and_check(
            self._ws_client,
            protocol_pb2.ModuleId.MODULE_CAMERA_TELE,
            protocol_pb2.DwarfCMD.CMD_CAMERA_TELE_CLOSE_CAMERA,
            request,
        )

    async def camera_start_exposure(self, duration: float, light: bool) -> None:
        state = self.camera_state
        state.duration = duration
        state.light = light
        state.start_time = time.time()
        state.last_start_time = state.start_time
        state.last_end_time = None
        state.image_timestamp = None
        state.last_error = None
        state.image = None
        state.capture_mode = "photo" if self.simulation else "astro"
        if state.capture_task and not state.capture_task.done():
            state.capture_task.cancel()
        if self.simulation:
            await self._simulate_capture(state)
            state.capture_task = None
            return

        await self._ensure_ws()
        await self._ensure_exposure_settings(duration)
        command_timeout = max(duration + 10.0, 20.0)
        fallback_to_photo = False

        await self._configure_astro_capture(frames=1)
        await self._refresh_capture_baseline(capture_kind=state.capture_mode)
        try:
            await self._start_astro_capture(timeout=command_timeout)
        except DwarfCommandError as exc:
            log_fields = {
                "duration": duration,
                "light": light,
                "module_id": exc.module_id,
                "command_id": exc.command_id,
                "error_code": exc.code,
            }
            if light and exc.code == protocol_pb2.CODE_ASTRO_NEED_GOTO:
                state.last_error = "astro_need_goto"
                log_fields["error_hint"] = "goto_required"
                log_fields["fallback"] = "tele_raw"
                logger.warning("dwarf.camera.astro_capture_command_failed", **log_fields)
                fallback_to_photo = True
            else:
                state.last_error = f"command_error:{exc.code}"
                logger.error("dwarf.camera.astro_capture_command_failed", **log_fields)
                raise

        if fallback_to_photo:
            state.capture_mode = "photo"
            await self._refresh_capture_baseline(capture_kind=state.capture_mode)
            try:
                await self._start_photo_capture(timeout=command_timeout)
            except DwarfCommandError as exc:
                state.last_error = f"command_error:{exc.code}"
                logger.error(
                    "dwarf.camera.tele_raw_capture_failed",
                    duration=duration,
                    light=light,
                    module_id=exc.module_id,
                    command_id=exc.command_id,
                    error_code=exc.code,
                )
                raise
            else:
                state.last_error = None
                logger.info(
                    "dwarf.camera.tele_raw_capture_started",
                    duration=duration,
                    light=light,
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
        resolver = await self._get_exposure_resolver()
        index = resolver.choose_index(duration) if resolver else None
        if index is None:
            logger.warning("dwarf.camera.exposure_index_missing", requested_duration=duration)
            return
        try:
            await self._set_exposure_mode_manual()
            await self._set_exposure_index(index)
        except Exception as exc:  # pragma: no cover - hardware dependent
            logger.warning(
                "dwarf.camera.exposure_config_failed",
                error=str(exc),
                requested_duration=duration,
                index=index,
            )

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
        if not self._params_config:
            return None
        data = self._params_config.get("data")
        if not isinstance(data, dict):
            return None
        params = data.get("featureParams")
        if not isinstance(params, list):
            return None
        needle = name.strip().lower()
        for entry in params:
            if not isinstance(entry, dict):
                continue
            entry_name = str(entry.get("name", "")).strip().lower()
            if entry_name == needle:
                return entry
        return None

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
            await send_and_check(
                self._ws_client,
                protocol_pb2.ModuleId.MODULE_CAMERA_TELE,
                protocol_pb2.DwarfCMD.CMD_CAMERA_TELE_SET_FEATURE_PARAM,
                request,
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

    async def _configure_astro_capture(self, *, frames: int = 1) -> None:
        if self.simulation:
            return
        config = await self._ensure_params_config()
        if config is None:
            return
        desired = (
            ("Astro binning", 0, 0, 0.0),
            ("Astro format", 0, 0, 0.0),
            ("Astro display source", 0, 1, 0.0),
            ("Astro ai enhance", 0, 0, 0.0),
        )
        for name, mode_index, index, continue_value in desired:
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

    async def _start_astro_capture(self, *, timeout: float) -> None:
        if self.simulation:
            return
        request = ReqAstroStartCaptureRawLiveStacking()
        await send_and_check(
            self._ws_client,
            protocol_pb2.ModuleId.MODULE_ASTRO,
            protocol_pb2.DwarfCMD.CMD_ASTRO_START_CAPTURE_RAW_LIVE_STACKING,
            request,
            timeout=timeout,
        )

    async def _start_photo_capture(self, *, timeout: float) -> None:
        if self.simulation:
            return
        request = ReqPhotoRaw()
        await send_and_check(
            self._ws_client,
            protocol_pb2.ModuleId.MODULE_CAMERA_TELE,
            protocol_pb2.DwarfCMD.CMD_CAMERA_TELE_PHOTO_RAW,
            request,
            timeout=timeout,
        )

    async def _stop_astro_capture(self) -> None:
        if self.simulation:
            return
        try:
            request = ReqAstroStopCaptureRawLiveStacking()
            await send_and_check(
                self._ws_client,
                protocol_pb2.ModuleId.MODULE_ASTRO,
                protocol_pb2.DwarfCMD.CMD_ASTRO_STOP_CAPTURE_RAW_LIVE_STACKING,
                request,
            )
        except Exception as exc:  # pragma: no cover - hardware dependent
            logger.debug("dwarf.astro.stop_capture_failed", error=str(exc))

    async def _set_exposure_mode_manual(self) -> None:
        request = ReqSetExpMode()
        request.mode = protocol_pb2.PhotoMode.Manual
        await send_and_check(
            self._ws_client,
            protocol_pb2.ModuleId.MODULE_CAMERA_TELE,
            protocol_pb2.DwarfCMD.CMD_CAMERA_TELE_SET_EXP_MODE,
            request,
        )

    async def _set_exposure_index(self, index: int) -> None:
        request = ReqSetExp()
        request.index = index
        await send_and_check(
            self._ws_client,
            protocol_pb2.ModuleId.MODULE_CAMERA_TELE,
            protocol_pb2.DwarfCMD.CMD_CAMERA_TELE_SET_EXP,
            request,
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

    async def _get_latest_album_entry(self) -> tuple[int | None, dict[str, Any] | None]:
        try:
            entries = await self._http_client.list_album_media_infos(media_type=1, page_size=1)
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
        if not self.simulation:
            ftp_success = False
            try:
                ftp_success = await self._attempt_ftp_capture(state)
            finally:
                if astro_mode:
                    await self._stop_astro_capture()
            if ftp_success:
                return
        if not astro_mode:
            await self._attempt_album_capture(state)

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
        while time.time() < deadline:
            mod_time, latest_entry = await self._get_latest_album_entry()
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
                await send_and_check(
                    self._ws_client,
                    protocol_pb2.ModuleId.MODULE_FOCUS,
                    protocol_pb2.DwarfCMD.CMD_FOCUS_STOP_MANUAL_CONTINU_FOCUS,
                    stop,
                )
        state.connected = False
        state.is_moving = False

    async def focuser_move(self, delta: int) -> None:
        state = self.focuser_state
        state.is_moving = True
        if self.simulation:
            await self._simulate_focus_move(delta)
            state.is_moving = False
            return

        await self._ensure_ws()
        direction = 1 if delta > 0 else 0
        steps = abs(delta)
        if steps == 0:
            state.is_moving = False
            return
        if steps <= 10:
            for _ in range(steps):
                request = ReqManualSingleStepFocus()
                request.direction = direction
                await send_and_check(
                    self._ws_client,
                    protocol_pb2.ModuleId.MODULE_FOCUS,
                    protocol_pb2.DwarfCMD.CMD_FOCUS_MANUAL_SINGLE_STEP_FOCUS,
                    request,
                )
                state.position += 1 if delta > 0 else -1
                state.position = max(0, min(state.position, 20000))
                await asyncio.sleep(0.02)
        else:
            request = ReqManualContinuFocus()
            request.direction = direction
            await send_and_check(
                self._ws_client,
                protocol_pb2.ModuleId.MODULE_FOCUS,
                protocol_pb2.DwarfCMD.CMD_FOCUS_START_MANUAL_CONTINU_FOCUS,
                request,
            )
            await asyncio.sleep(min(steps * 0.01, 5))
            stop = ReqStopManualContinuFocus()
            await send_and_check(
                self._ws_client,
                protocol_pb2.ModuleId.MODULE_FOCUS,
                protocol_pb2.DwarfCMD.CMD_FOCUS_STOP_MANUAL_CONTINU_FOCUS,
                stop,
            )
            state.position += delta
            state.position = max(0, min(state.position, 20000))
        state.is_moving = False

    async def focuser_halt(self) -> None:
        state = self.focuser_state
        if self.simulation:
            state.is_moving = False
            return
        await self._ensure_ws()
        stop = ReqStopManualContinuFocus()
        try:
            await send_and_check(
                self._ws_client,
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


async def get_session() -> DwarfSession:
    global _session
    if _session is None:
        async with _session_lock:
            if _session is None:
                settings = _session_settings or Settings()
                _session = DwarfSession(settings)
    return _session
