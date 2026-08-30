from __future__ import annotations

import asyncio
import contextlib
import math
import re
import struct
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, IntEnum
from typing import Any, Dict, Iterator, Optional, Tuple, Type

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover - Python < 3.9 or missing tzdata
    ZoneInfo = None  # type: ignore[assignment]

import numpy as np
import structlog
from google.protobuf.json_format import MessageToDict
from google.protobuf.message import Message
from websockets.exceptions import ConnectionClosed, ConnectionClosedOK

from ..astronomy.target_names import resolve_nina_target_name
from ..config.settings import Settings
from ..device_profile import DeviceProfile, get_device_profile
from ..proto import astro_pb2, protocol_pb2
from ..proto.astro_pb2 import ReqGotoDSO, ReqStopGoto
from ..proto.base_pb2 import CommonParam, ComResponse
from ..proto.camera_pb2 import (
    ReqCloseCamera,
    ReqGetAllFeatureParams,
    ReqGetSystemWorkingState,
    ReqOpenCamera,
    ReqPhoto,
    ReqPhotoRaw,
    ReqSetExp,
    ReqSetExpMode,
    ReqSetFeatureParams,
    ReqSetGain,
    ReqSetGainMode,
    ReqSetIrCut,
    ReqSetPreviewQuality,
    ResGetAllFeatureParams,
)
from ..proto.dwarf_messages import (
    ResNotifyFocus,
    ResNotifyHostSlaveMode,
    ResNotifyParam,
    ResNotifyStateAstroGoto,
    ResNotifyStateAstroTracking,
    ResNotifyTemperature,
    V3ResNotifyExposureProgress,
)
from ..proto.focus_pb2 import (
    ReqAstroAutoFocus,
    ReqGetUserInfinityPos,
    ReqManualContinuFocus,
    ReqManualSingleStepFocus,
    ReqStopManualContinuFocus,
    ResUserInfinityPos,
)
from ..proto.motor_control_pb2 import (
    ReqMotorServiceJoystick,
    ReqMotorServiceJoystickStop,
)
from ..proto.notify_pb2 import (
    AstroAutoFocusFastState,
    AstroAutoFocusState,
    AstroCalibrationState,
    CalibrationResult,
    CmosTemperature,
    GeneralIntParam,
    LongExpPhotoProgress,
    OneClickGotoState,
    ProgressCaptureRawLiveStacking,
    SkyTargetFinderState,
    SwitchShootingMode,
)
from ..proto.param_pb2 import ReqSetExposure, ReqSetGeneralIntParam
from ..proto.system_pb2 import ReqsetMasterLock, ReqSetTime, ReqSetTimezone
from ..proto.task_center_pb2 import (
    ReqEnterCamera,
    ReqGetDeviceStateInfo,
    ReqSwitchShootingMode,
    ReqSwitchShootingTech,
    ResEnterCamera,
    ResGetDeviceStateInfo,
    ResNotifyTaskState,
    ResSwitchShootingMode,
    ResSwitchShootingTech,
)
from . import exposure
from .ftp_client import DwarfFtpClient, FtpPhotoEntry
from .http_client import DwarfHttpClient
from .ws_client import DwarfCommandError, DwarfWsClient, send_and_check

logger = structlog.get_logger(__name__)


def _read_varint(raw: bytes, start: int) -> tuple[int, int]:
    value = 0
    shift = 0
    index = start
    while index < len(raw):
        byte = raw[index]
        index += 1
        value |= (byte & 0x7F) << shift
        if (byte & 0x80) == 0:
            return value, index
        shift += 7
        if shift >= 64:
            break
    raise ValueError("invalid varint")


def _decode_com_res_with_int_value(raw: bytes) -> int | None:
    index = 0
    while index < len(raw):
        try:
            key, index = _read_varint(raw, index)
        except ValueError:
            return None
        field = key >> 3
        wire_type = key & 0x07
        if wire_type == 0:
            try:
                value, index = _read_varint(raw, index)
            except ValueError:
                return None
            if field == 1:
                if value >= (1 << 31):
                    value -= 1 << 32
                return int(value)
            continue
        if wire_type == 1:
            index += 8
            continue
        if wire_type == 2:
            try:
                length, index = _read_varint(raw, index)
            except ValueError:
                return None
            index += int(length)
            continue
        if wire_type == 5:
            index += 4
            continue
        return None
    return None


def _length_delimited_field(raw: bytes, wanted_field: int) -> bytes | None:
    """Return one protobuf length-delimited field without requiring its schema."""

    index = 0
    while index < len(raw):
        try:
            key, index = _read_varint(raw, index)
        except ValueError:
            return None
        field = key >> 3
        wire_type = key & 0x07
        if wire_type == 0:
            try:
                _value, index = _read_varint(raw, index)
            except ValueError:
                return None
            continue
        if wire_type == 1:
            index += 8
            continue
        if wire_type == 2:
            try:
                length, index = _read_varint(raw, index)
            except ValueError:
                return None
            end = index + int(length)
            if end > len(raw):
                return None
            value = raw[index:end]
            if field == wanted_field:
                return value
            index = end
            continue
        if wire_type == 5:
            index += 4
            continue
        return None
    return None


def _decode_v3_device_config_payload(raw: bytes) -> dict[str, Any]:
    result: dict[str, Any] = {}
    index = 0
    while index < len(raw):
        try:
            key, index = _read_varint(raw, index)
        except ValueError:
            break
        field = key >> 3
        wire_type = key & 0x07

        if wire_type == 0:
            try:
                value, index = _read_varint(raw, index)
            except ValueError:
                break
            if field == 5:
                result["image_width"] = int(value)
            elif field == 6:
                result["image_height"] = int(value)
            else:
                result[f"field{field}_varint"] = int(value)
            continue

        if wire_type == 1:
            if index + 8 > len(raw):
                break
            chunk = raw[index : index + 8]
            index += 8
            value = struct.unpack("<d", chunk)[0]
            if field == 3:
                result["field3_double"] = float(value)
            elif field == 4:
                result["field4_double"] = float(value)
            else:
                result[f"field{field}_double"] = float(value)
            continue

        if wire_type == 2:
            try:
                length, index = _read_varint(raw, index)
            except ValueError:
                break
            length = int(length)
            if index + length > len(raw):
                break
            data = raw[index : index + length]
            index += length
            if field == 1:
                result["field1_blob_len"] = length
                # CMD 16405 is the APK's GetDeviceStateInfo request. Field 2
                # of its response is TeleCameraStateInfo, which this legacy
                # compatibility decoder receives as ``raw``. Its field 1 is
                # ExclusiveCameraState; that message's field 1 is
                # CaptureRawState { state=1, camera_type=2 }.
                capture_raw = _length_delimited_field(data, 1)
                if capture_raw is not None:
                    capture_state = _decode_com_res_with_int_value(capture_raw)
                    if capture_state is not None:
                        result["capture_raw_state"] = int(capture_state)
            elif field == 2:
                result["field2_blob_hex"] = data.hex()
                # Observed as nested payload `08 01` / `08 02`.
                if len(data) >= 2 and data[0] == 0x08:
                    try:
                        nested_value, _ = _read_varint(data, 1)
                        result["field2_mode"] = int(nested_value)
                    except ValueError:
                        pass
            else:
                result[f"field{field}_blob_len"] = length
            continue

        if wire_type == 5:
            if index + 4 > len(raw):
                break
            index += 4
            continue

        break

    width = result.get("image_width")
    height = result.get("image_height")
    if isinstance(width, int) and isinstance(height, int) and height > 0:
        result["image_aspect_ratio"] = round(width / height, 6)

    # Provide a compatibility-oriented view resembling the legacy HTTP camera block.
    fv_width = result.get("field3_double")
    fv_height = result.get("field4_double")
    if isinstance(width, int) and isinstance(height, int):
        legacy_camera: dict[str, Any] = {
            "id": 0,
            "name": "Tele",
            "previewWidth": width,
            "previewHeight": height,
        }
        if isinstance(fv_width, float):
            legacy_camera["fvWidth"] = fv_width
        if isinstance(fv_height, float):
            legacy_camera["fvHeight"] = fv_height
        result["legacy_camera"] = legacy_camera
    return result


FALLBACK_FILTER_LABELS = ["VIS Filter", "Astro Filter", "Duo-Band Filter"]
FALLBACK_FILTER_LABELS_MINI = ["Astro", "Duo-Band"]
_MINI_CANONICAL_FILTER_LABELS = tuple(FALLBACK_FILTER_LABELS_MINI)

_MAX_JOYSTICK_SPEED = 30.0
_MIN_JOYSTICK_SPEED = 0.1

_GOTO_KIND_DSO = "dso"

_MODULE_CAMERA_PARAMS = int(protocol_pb2.ModuleId.MODULE_CAMERA_PARAMS)
_MODULE_DEVICE_CONFIG = int(protocol_pb2.ModuleId.MODULE_DEVICE_CONFIG)
_CMD_PARAM_SET_EXPOSURE = int(protocol_pb2.DwarfCMD.CMD_PARAM_SET_EXPOSURE)
_CMD_PARAM_SET_GAIN = int(protocol_pb2.DwarfCMD.CMD_PARAM_SET_GAIN)
_CMD_PARAM_SET_GENERAL_INT = int(protocol_pb2.DwarfCMD.CMD_PARAM_SET_GENERAL_INT_PARAM)
_V3_ASTRO_MODE_ID = 2
_V3_ASTRO_CAPTURE_MODE_ID = 11
_V3_PARAM_MODE_SHIFT = 56
_V3_PARAM_MODE_VALUE_MASK = (1 << _V3_PARAM_MODE_SHIFT) - 1
_V3_ASTRO_EXPOSURE_PARAM_ID = 0x0201000000000001
_V3_ASTRO_GAIN_PARAM_ID = 0x0201000000000002
_CMD_TASK_SWITCH_SHOOTING_MODE = int(
    protocol_pb2.DwarfCMD.CMD_GLOBAL_TASK_MANAGER_SWITCH_SHOOTING_MODE
)
_CMD_TASK_SWITCH_SHOOTING_TECH = int(
    protocol_pb2.DwarfCMD.CMD_GLOBAL_TASK_MANAGER_SWITCH_SHOOTING_TECH
)
_CMD_TASK_ENTER_CAMERA = int(protocol_pb2.DwarfCMD.CMD_GLOBAL_TASK_MANAGER_ENTER_CAMERA)
_CMD_TASK_GET_DEVICE_STATE = int(protocol_pb2.DwarfCMD.CMD_GLOBAL_TASK_GET_DEVICE_STATE_INFO)
_CMD_FOCUS_GET_USER_INFINITY_POS = int(protocol_pb2.DwarfCMD.CMD_FOCUS_GET_USER_INFINITY_POS)
_CMD_NOTIFY_WAIT_SHOOTING_PROGRESS = int(
    protocol_pb2.DwarfCMD.CMD_NOTIFY_WAIT_SHOOTING_PROGRESS
)
_CMD_NOTIFY_EXCLUSIVE_SYSTEM_IO_TASK_STATE = int(
    protocol_pb2.DwarfCMD.CMD_NOTIFY_EXCLUSIVE_SYSTEM_IO_TASK_STATE
)
_CMD_NOTIFY_GENERAL_INT_PARAM = int(protocol_pb2.DwarfCMD.CMD_NOTIFY_GENERAL_INT_PARAM)
_CMD_NOTIFY_SWITCH_SHOOTING_MODE = int(
    protocol_pb2.DwarfCMD.CMD_NOTIFY_SWITCH_SHOOTING_MODE
)
_CMD_NOTIFY_CMOS_TEMPERATURE = int(protocol_pb2.DwarfCMD.CMD_NOTIFY_CMOS_TEMPERATURE)
_CMD_NOTIFY_SKY_TARGET_FINDER_STATE = int(
    protocol_pb2.DwarfCMD.CMD_NOTIFY_SKY_TARGET_FINDER_STATE
)
# Observed on mini firmware captures for V3 filterwheel adjust writes.
_MINI_DEFAULT_FILTER_PARAM_ID = 0x20100000000000D
_MINI_ALT_FILTER_PARAM_ID = 0x100000000000D
# Captured from the DWARF 3 app immediately after setting astronomy parameters.
# Without this dedicated write the firmware can retain an earlier value (for
# example 999) from a previous capture workflow.
_V3_ASTRO_FRAME_COUNT_PARAM_ID = 0x202000000000010
_ASTRO_FORCE_START_DARK_WARNING_CODES = frozenset(
    {
        protocol_pb2.CODE_ASTRO_DARK_NOT_FOUND,
        protocol_pb2.CODE_ASTRO_DARK_TEMP_MISMATCH,
    }
)
_ASTRO_NON_FATAL_START_WARNING_CODES = frozenset(
    {
        protocol_pb2.CODE_ASTRO_NEED_GOTO,
        protocol_pb2.CODE_ASTRO_NEED_ADJUST_SHOOT_PARAM,
    }
)


def _resolve_ws_protocol_profile(settings: Settings) -> tuple[int, int]:
    """Return websocket defaults from the centralized capability profile."""

    protocol = get_device_profile(settings.dwarf_device_model).protocol
    return (protocol.ws_minor_version, protocol.ws_device_id)


def resolve_ws_client_id(settings: Settings) -> str:
    """Use a model-specific ID unless the operator explicitly supplied one."""

    if "dwarf_ws_client_id" in settings.model_fields_set:
        return settings.dwarf_ws_client_id
    return get_device_profile(settings.dwarf_device_model).ws_client_id


class _AstroState(IntEnum):
    IDLE = 0
    RUNNING = 1
    STOPPING = 2
    STOPPED = 3
    PLATE_SOLVING = 4


class _OperationState(IntEnum):
    IDLE = 0
    RUNNING = 1
    STOPPING = 2
    STOPPED = 3


class CapturePhase(str, Enum):
    IDLE = "idle"
    CONFIGURING = "configuring"
    WAITING_FOR_DARK = "waiting_for_dark"
    STARTING = "starting"
    EXPOSING = "exposing"
    PROCESSING = "processing"
    TRANSFERRING = "transferring"
    READY = "ready"
    ABORTING = "aborting"
    FAILED = "failed"
    UNKNOWN = "unknown"


class CaptureBusyError(RuntimeError):
    """Raised when a second exposure overlaps an active capture."""


class CaptureConfigurationError(RuntimeError):
    """Raised when a requested capture setting cannot be proved applied."""


@dataclass(frozen=True)
class V3AstroPreset:
    exposure_s: float
    gain: int
    resolution_index: int
    pipe_parts: tuple[str, ...]


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
    capture_mode: str = "astro"
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
    dark_status: str = "unknown"
    last_album_mod_time: int | None = None
    last_album_file: str | None = None
    pending_album_baseline: int | None = None
    last_ftp_entry: "FtpPhotoEntry | None" = field(default=None, repr=False)
    pending_ftp_baseline: "FtpPhotoEntry | None" = field(default=None, repr=False)
    temperature_c: float | None = None
    last_temperature_time: float | None = None
    last_temperature_code: int | None = None
    battery_percent: int | None = None
    last_battery_time: float | None = None
    reported_preview_width: int | None = None
    reported_preview_height: int | None = None
    reported_fv_width: float | None = None
    reported_fv_height: float | None = None
    requested_gain: int | None = None
    applied_gain_index: int | None = None
    applied_gain_value: int | None = None
    applied_duration: float | None = None
    reported_duration: float | None = None
    applied_filter_name: str | None = None
    applied_bin: tuple[int, int] | None = None
    applied_frame_count: int | None = None
    requested_bin: tuple[int, int] = (1, 1)
    requested_frame_count: int = 1
    capture_id: str | None = None
    capture_phase: CapturePhase = CapturePhase.IDLE
    capture_start_monotonic: float | None = None
    source_format: str | None = None
    source_bit_depth: int | None = None
    progress_total_count: int | None = None
    progress_current_count: int = 0
    progress_stacked_count: int = 0
    progress_exposure_index: int | None = None
    progress_gain_index: int | None = None
    progress_target_name: str | None = None
    retrieved_file_path: str | None = None


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
        self.profile: DeviceProfile = get_device_profile(settings.dwarf_device_model)
        self.simulation = settings.force_simulation
        self._observer_latitude = settings.site_latitude
        self._observer_longitude = settings.site_longitude
        ws_minor_version, ws_device_id = _resolve_ws_protocol_profile(settings)
        self._ws_client = DwarfWsClient(
            settings.dwarf_ap_ip,
            port=settings.dwarf_ws_port,
            major_version=1,
            minor_version=ws_minor_version,
            device_id=ws_device_id,
            client_id=resolve_ws_client_id(settings),
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
        self._ws_command_lock: asyncio.Lock | None = None
        self._ws_command_lock_loop: asyncio.AbstractEventLoop | None = None
        self._filter_change_lock: asyncio.Lock | None = None
        self._filter_change_lock_loop: asyncio.AbstractEventLoop | None = None
        self._capture_start_evidence_event = asyncio.Event()
        self._capture_frame_complete_event = asyncio.Event()
        self._astro_capture_ready_event = asyncio.Event()
        self._astro_capture_ready_event.set()
        self._astro_capture_operation_state: int | None = None
        self._capture_start_response_task: asyncio.Task[None] | None = None
        self._capture_stop_response_task: asyncio.Task[None] | None = None
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
        self._last_goto_kind: str | None = None
        self._goto_completion_event = asyncio.Event()
        self._goto_completion_event.set()
        self._goto_result: str | None = None
        self._goto_reason: str | None = None
        self._goto_pending = False
        self._goto_waiting_for_tracking = False
        self._goto_target_name: str | None = None
        self._goto_start_time: float | None = None
        self._one_click_goto_active = False
        self._one_click_response_task: asyncio.Task[None] | None = None
        self._time_synced = self.simulation
        self._last_time_sync_offset: float | None = None
        self._last_time_sync_timezone: str | None = None
        self._gain_command_supported: bool | None = None
        self._gain_command_warning_logged = False
        self._gain_support_param: dict[str, Any] | None = None
        self._gain_value_options: list[tuple[int, int]] | None = None
        self._gain_manual_mode_supported: bool | None = None
        self._gain_last_skipped_value: int | None = None
        self._ws_feature_params: list[dict[str, Any]] | None = None
        self._ws_v3_filter_param_id: int | None = None
        self._ws_v3_filter_param_flag: int = 0
        self._ws_v3_filter_value: int | None = None
        self._v3_device_state_event: int | None = None
        self._v3_device_state_mode: int | None = None
        self._v3_device_state_detail: int | None = None
        self._v3_device_state_path: str | None = None
        self._v3_mode_change: tuple[int, int, int] | None = None
        self._v3_observation_state: int | None = None
        self._v3_exposure_progress: tuple[int, int] | None = None
        self._v3_device_config_bytes: int | None = None
        self._v3_astro_presets: list[V3AstroPreset] | None = None
        self._v3_selected_astro_preset: V3AstroPreset | None = None
        self._v3_astro_param_catalog: dict[str, Any] | None = None
        self._v3_live_parameters_supported: bool | None = None
        self._v3_runtime_reapply_capture_id: str | None = None
        self._v3_capture_param_mode_id: int | None = None
        self._calibration_lock = asyncio.Lock()
        self._last_calibration_time: float | None = None
        self._last_calibration_ip: str | None = None
        self._calibration_task = None  # type: asyncio.Task[None] | None
        self._calibration_result_event = asyncio.Event()
        self._autofocus_completion_event = asyncio.Event()
        self._calibration_autofocus_time: float | None = None
        self._calibration_autofocus_ip: str | None = None
        self._calibration_status = "unknown"
        self._calibration_detail: str | None = None
        self._calibration_azimuth: float | None = None
        self._calibration_altitude: float | None = None
        self._calibration_trace_started: float | None = None
        self._calibration_trace_last_state: float | None = None
        self._calibration_trace_notifications = 0

    @property
    def is_simulated(self) -> bool:
        return self.simulation

    @property
    def has_master_lock(self) -> bool:
        return self._master_lock_acquired

    def _is_dwarf_mini(self) -> bool:
        return self.profile.model_id == "dwarfmini"

    def set_observer_location(
        self,
        *,
        latitude: float | None = None,
        longitude: float | None = None,
    ) -> None:
        """Update the observer coordinates used by V3 calibration commands."""

        if latitude is not None and not -90.0 <= latitude <= 90.0:
            raise ValueError("Latitude must be between -90 and 90 degrees")
        if longitude is not None and not -180.0 <= longitude <= 180.0:
            raise ValueError("Longitude must be between -180 and 180 degrees")
        changed = False
        if latitude is not None and latitude != self._observer_latitude:
            self._observer_latitude = latitude
            changed = True
        if longitude is not None and longitude != self._observer_longitude:
            self._observer_longitude = longitude
            changed = True
        if not changed:
            return
        self.settings = self.settings.model_copy(
            update={
                "site_latitude": self._observer_latitude,
                "site_longitude": self._observer_longitude,
            }
        )
        self._last_calibration_time = None
        self._last_calibration_ip = None
        logger.info(
            "dwarf.telescope.observer_location.updated",
            latitude=self._observer_latitude,
            longitude=self._observer_longitude,
        )

    def _require_observer_location(self) -> tuple[float, float]:
        latitude = self._observer_latitude
        longitude = self._observer_longitude
        if latitude is None or longitude is None or (latitude == 0.0 and longitude == 0.0):
            raise RuntimeError(
                "Observer latitude and longitude are required for V3 mount calibration"
            )
        if not -90.0 <= latitude <= 90.0 or not -180.0 <= longitude <= 180.0:
            raise RuntimeError("Observer coordinates are outside the supported range")
        return (latitude, longitude)

    def _uses_v3_protocol(self) -> bool:
        return self.profile.protocol.family == "v3"

    def _resolve_mini_capture_mode(self) -> str:
        mode = (
            str(getattr(self.settings, "dwarf_mini_capture_mode", "astro") or "astro")
            .strip()
            .lower()
        )
        if mode not in {"astro", "photo"}:
            logger.warning(
                "dwarf.camera.mini_capture_mode_invalid", configured=mode, fallback="astro"
            )
            return "astro"
        return mode

    def _fallback_filter_labels(self) -> list[str]:
        if self._is_dwarf_mini():
            return FALLBACK_FILTER_LABELS_MINI
        return FALLBACK_FILTER_LABELS

    def get_v3_runtime_state(self) -> dict[str, Any]:
        return {
            "is_mini": self._is_dwarf_mini(),
            "ws_minor_version": int(getattr(self._ws_client, "minor_version", 0)),
            "ws_device_id": int(getattr(self._ws_client, "device_id", 0)),
            "device_state_event": self._v3_device_state_event,
            "device_state_mode": self._v3_device_state_mode,
            "device_state_detail": self._v3_device_state_detail,
            "device_state_path": self._v3_device_state_path,
            "mode_change": list(self._v3_mode_change) if self._v3_mode_change else None,
            "observation_state": self._v3_observation_state,
            "exposure_progress": list(self._v3_exposure_progress)
            if self._v3_exposure_progress
            else None,
            "device_config_bytes": self._v3_device_config_bytes,
        }

    def get_calibration_status(self) -> dict[str, Any]:
        """Return the latest firmware-confirmed mount calibration outcome."""
        return {
            "status": self._calibration_status,
            "detail": self._calibration_detail,
            "azimuth": self._calibration_azimuth,
            "altitude": self._calibration_altitude,
            "calibrated_at": self._last_calibration_time,
        }

    def _capture_evidence_snapshot(self) -> tuple[object, ...]:
        return (
            self._v3_exposure_progress,
            self._v3_observation_state,
            self._v3_device_state_event,
            self._v3_device_state_detail,
            self._v3_device_state_path,
        )

    def _normalize_filter_label(self, label: str, index: int) -> str:
        resolved = _canonical_filter_label(label, index)
        if not self._is_dwarf_mini():
            return resolved
        lowered = resolved.strip().lower().replace("_", " ")
        lowered = " ".join(part for part in lowered.split() if part)
        if "duo" in lowered and "band" in lowered:
            return "Duo-Band"
        if lowered in {"astro", "astro filter"}:
            return "Astro"
        return resolved

    @staticmethod
    def _looks_like_filter_option_set(labels: list[str]) -> bool:
        canonical: set[str] = set()
        for raw in labels:
            lowered = str(raw).strip().lower().replace("_", " ")
            lowered = " ".join(part for part in lowered.split() if part)
            if not lowered:
                continue
            if "duo" in lowered and "band" in lowered:
                canonical.add("duoband")
            if lowered in {"dark", "dark filter", "astro", "astro filter"}:
                canonical.add("dark")
            if lowered in {"vis", "vis filter", "no filter", "none", "clear"}:
                canonical.add("clear")
        return len(canonical) >= 2

    @staticmethod
    def _decode_v3_param_id(param_id: int) -> tuple[int, int, int, int]:
        value = int(param_id) & 0xFFFFFFFF
        shooting_mode = (value >> 24) & 0xFF
        category = (value >> 16) & 0xFF
        camera_id = (value >> 8) & 0xFF
        param_index = value & 0xFF
        return shooting_mode, category, camera_id, param_index

    def _is_likely_filter_param_id(self, param_id: int | None) -> bool:
        if param_id is None:
            return False
        try:
            value = int(param_id)
        except (TypeError, ValueError):
            return False
        if value <= 0:
            return False
        if value < 256:
            return value in {8, 13}
        _, _, camera_id, param_index = self._decode_v3_param_id(value)
        return camera_id == 0 and param_index in {8, 13}

    def _canonical_mini_filter_bucket(self, label: str) -> str | None:
        normalized = self._normalize_filter_label(label, 0)
        if normalized in _MINI_CANONICAL_FILTER_LABELS:
            return normalized
        return None

    def _canonicalize_mini_filter_options(self, options: list[FilterOption]) -> list[FilterOption]:
        if not self._is_dwarf_mini():
            return options
        if not options:
            return options

        bucketed: dict[str, FilterOption] = {}
        remaining: list[FilterOption] = []
        for option in options:
            bucket = self._canonical_mini_filter_bucket(option.label)
            if bucket is None:
                remaining.append(option)
                continue
            bucketed.setdefault(bucket, option)

        ordered: list[FilterOption] = []
        for label in _MINI_CANONICAL_FILTER_LABELS:
            chosen = bucketed.get(label)
            if chosen is not None:
                ordered.append(
                    FilterOption(
                        parameter=chosen.parameter,
                        mode_index=chosen.mode_index,
                        index=chosen.index,
                        label=label,
                        continue_value=chosen.continue_value,
                        controllable=chosen.controllable,
                    )
                )
                continue

            fallback_position = _MINI_CANONICAL_FILTER_LABELS.index(label)
            ordered.append(
                FilterOption(
                    parameter=None,
                    mode_index=0,
                    index=fallback_position,
                    label=label,
                    continue_value=None,
                    controllable=False,
                )
            )

        if remaining:
            logger.debug(
                "dwarf.camera.filter_options_mini_extra_ignored",
                extra_labels=[entry.label for entry in remaining],
            )
        return ordered

    def _get_ws_command_lock(self) -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        lock = self._ws_command_lock
        if lock is None or self._ws_command_lock_loop is not loop:
            lock = asyncio.Lock()
            self._ws_command_lock = lock
            self._ws_command_lock_loop = loop
        return lock

    def _reset_ws_command_lock(self) -> None:
        self._ws_command_lock = None
        self._ws_command_lock_loop = None

    def _get_filter_change_lock(self) -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        lock = self._filter_change_lock
        if lock is None or self._filter_change_lock_loop is not loop:
            lock = asyncio.Lock()
            self._filter_change_lock = lock
            self._filter_change_lock_loop = loop
        return lock

    async def _handle_ws_timeout(self, module_id: int, command_id: int, error: Exception) -> None:
        await self._handle_ws_timeout_with_options(
            module_id,
            command_id,
            error,
            log_as_warning=True,
            close_ws=True,
        )

    async def _handle_ws_timeout_with_options(
        self,
        module_id: int,
        command_id: int,
        error: Exception,
        *,
        log_as_warning: bool,
        close_ws: bool,
    ) -> None:
        log_method = logger.warning if log_as_warning else logger.debug
        log_method(
            "dwarf.ws.command.timeout",
            module_id=module_id,
            command_id=command_id,
            error=str(error),
            error_type=type(error).__name__,
        )
        self._ws_client.cancel_pending(module_id, command_id, error)
        if close_ws:
            self._reset_ws_command_lock()
            with contextlib.suppress(Exception):
                await self._ws_client.close()

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
            if self._last_calibration_ip != self.settings.dwarf_ap_ip:
                self._last_calibration_time = None
                self._last_calibration_ip = None
        await self._ensure_master_lock()
        self._ensure_temperature_monitor_task()

    async def _bootstrap_ws(self) -> None:
        if self.simulation or self._ws_bootstrapped or not self._ws_client.connected:
            return

        # V3 devices use the device-config bootstrap below, not V2 camera probes.
        if self._uses_v3_protocol():
            self._ws_bootstrapped = True
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

    async def _bootstrap_v3_state(self) -> None:
        if self.simulation or not self._uses_v3_protocol() or not self._ws_client.connected:
            return

        config_request = ReqGetDeviceStateInfo()
        try:
            response = await self._send_request(
                _MODULE_DEVICE_CONFIG,
                _CMD_TASK_GET_DEVICE_STATE,
                config_request,
                ResGetDeviceStateInfo,
                timeout=5.0,
                suppress_timeout_warning=True,
                close_ws_on_timeout=False,
            )
            if isinstance(response, ResGetDeviceStateInfo):
                self._v3_device_config_bytes = len(response.SerializeToString())
                parsed = self._apply_v3_device_state_info(response)
                logger.info(
                    "dwarf.system.v3_device_state_info",
                    code=int(response.code),
                    shooting_mode=int(response.shooting_mode),
                    payload_len=self._v3_device_config_bytes,
                    parsed=parsed,
                )
        except Exception as exc:  # pragma: no cover - hardware dependent
            logger.debug("dwarf.system.v3_device_config_failed", error=str(exc))

    async def _enter_v3_astro_mode(self) -> None:
        """Put a V3 device into the Deep Sky workflow before applying astro parameters."""

        if self.simulation or not self._uses_v3_protocol():
            return

        mode_switch = ReqSwitchShootingMode(mode=8)
        mode_response = await self._send_request(
            _MODULE_DEVICE_CONFIG,
            _CMD_TASK_SWITCH_SHOOTING_MODE,
            mode_switch,
            ResSwitchShootingMode,
            timeout=8.0,
        )
        mode_code = int(getattr(mode_response, "code", protocol_pb2.OK))
        mode = int(getattr(mode_response, "shooting_mode_id", 0))
        if mode_code != protocol_pb2.OK or mode != 8:
            raise CaptureConfigurationError(
                f"{self.profile.display_name} did not select astronomy mode "
                f"(code {mode_code}, mode {mode})"
            )

        enter_request = ReqEnterCamera()
        enter_request.client_param.encode_type = 1
        enter_response = await self._send_request(
            _MODULE_DEVICE_CONFIG,
            _CMD_TASK_ENTER_CAMERA,
            enter_request,
            ResEnterCamera,
            timeout=8.0,
        )
        enter_code = int(getattr(enter_response, "code", protocol_pb2.OK))
        entered_mode = int(getattr(enter_response, "shooting_mode_id", 0))
        # Current hardware reports 8; earlier V3 captures returned 2 for this
        # same enter-camera transition. Both are direct device evidence.
        if enter_code != protocol_pb2.OK or entered_mode not in {2, 8}:
            raise CaptureConfigurationError(
                f"{self.profile.display_name} did not enter the astronomy camera "
                f"(code {enter_code}, mode {entered_mode})"
            )

        tech_request = ReqSwitchShootingTech(tech=2)
        tech_response = await self._send_request(
            _MODULE_DEVICE_CONFIG,
            _CMD_TASK_SWITCH_SHOOTING_TECH,
            tech_request,
            ResSwitchShootingTech,
            timeout=8.0,
        )
        tech_code = int(getattr(tech_response, "code", protocol_pb2.OK))
        technique = int(getattr(tech_response, "shooting_tech_id", 0))
        if tech_code != protocol_pb2.OK or technique != 2:
            raise CaptureConfigurationError(
                f"{self.profile.display_name} did not select Deep Sky stacking "
                f"(code {tech_code}, technique {technique})"
            )

        preview = ReqSetPreviewQuality(level=1)
        await self._send_and_check(
            protocol_pb2.ModuleId.MODULE_CAMERA_TELE,
            protocol_pb2.DwarfCMD.CMD_CAMERA_TELE_SET_PREVIEW_QUALITY,
            preview,
            timeout=8.0,
        )
        logger.info(
            "dwarf.camera.v3_astro_mode_ready",
            device_mode=mode,
            shooting_technique=technique,
        )

    async def _handle_notification(self, packet: Message) -> None:
        if self.camera_state.capture_id is not None:
            raw_data = bytes(getattr(packet, "data", b"") or b"")
            command_id_for_trace = int(getattr(packet, "cmd", 0))
            module_id_for_trace = int(getattr(packet, "module_id", 0))
            logger.info(
                "dwarf.camera.capture.trace.packet",
                capture_id=self.camera_state.capture_id,
                module_id=module_id_for_trace,
                module_name=self._enum_name(protocol_pb2.ModuleId, module_id_for_trace),
                command_id=command_id_for_trace,
                command_name=self._enum_name(protocol_pb2.DwarfCMD, command_id_for_trace),
                packet_type=int(getattr(packet, "type", 0)),
                payload_length=len(raw_data),
                payload_hex=raw_data[:512].hex(),
                payload_truncated=len(raw_data) > 512,
            )
        self._trace_calibration_notification(packet)
        module_id = getattr(packet, "module_id", None)
        command_id = getattr(packet, "cmd", None)
        # Camera parameter notifications are emitted by MODULE_CAMERA_PARAMS
        # (15) on current DWARF 3 firmware, not MODULE_NOTIFY (9). Process them
        # before the generic notification-module guard.
        if (
            module_id == _MODULE_CAMERA_PARAMS
            and command_id == _CMD_NOTIFY_GENERAL_INT_PARAM
        ):
            self._handle_v3_camera_param_state_notification(packet)
            return
        if module_id != protocol_pb2.ModuleId.MODULE_NOTIFY:
            return
        if command_id == protocol_pb2.DwarfCMD.CMD_NOTIFY_FOCUS_POSITION:
            self._handle_focus_notification(packet)
        elif command_id == protocol_pb2.DwarfCMD.CMD_NOTIFY_TEMPERATURE:
            self._handle_temperature_notification(packet)
        elif command_id == protocol_pb2.DwarfCMD.CMD_NOTIFY_STATE_ASTRO_CALIBRATION:
            self._handle_calibration_state_notification(packet)
        elif command_id == protocol_pb2.DwarfCMD.CMD_NOTIFY_STATE_ASTRO_GOTO:
            self._handle_goto_state_notification(packet)
        elif command_id == protocol_pb2.DwarfCMD.CMD_NOTIFY_STATE_ASTRO_ONE_CLICK_GOTO:
            self._handle_one_click_goto_state_notification(packet)
        elif command_id == protocol_pb2.DwarfCMD.CMD_NOTIFY_CALIBRATION_RESULT:
            self._handle_calibration_result_notification(packet)
        elif command_id == protocol_pb2.DwarfCMD.CMD_NOTIFY_STATE_ASTRO_TRACKING:
            self._handle_tracking_state_notification(packet)
        elif command_id == protocol_pb2.DwarfCMD.CMD_NOTIFY_SET_FEATURE_PARAM:
            self._handle_feature_param_notification(packet)
        elif command_id == protocol_pb2.DwarfCMD.CMD_NOTIFY_STATE_CAPTURE_RAW_LIVE_STACKING:
            self._handle_astro_capture_state_notification(packet)
        elif command_id == protocol_pb2.DwarfCMD.CMD_NOTIFY_PROGRASS_CAPTURE_RAW_LIVE_STACKING:
            self._handle_astro_capture_progress_notification(packet)
        elif command_id == _CMD_NOTIFY_WAIT_SHOOTING_PROGRESS:
            self._handle_v3_exposure_progress_notification(packet)
        elif command_id == _CMD_NOTIFY_EXCLUSIVE_SYSTEM_IO_TASK_STATE:
            self._handle_v3_device_state_notification(packet)
        elif command_id == _CMD_NOTIFY_GENERAL_INT_PARAM:
            self._handle_v3_camera_param_state_notification(packet)
        elif command_id == _CMD_NOTIFY_SWITCH_SHOOTING_MODE:
            self._handle_v3_mode_change_notification(packet)
        elif command_id in {
            protocol_pb2.DwarfCMD.CMD_NOTIFY_ASTRO_AUTO_FOCUS_STATE,
            protocol_pb2.DwarfCMD.CMD_NOTIFY_ASTRO_AUTO_FOCUS_FAST_STATE,
        }:
            self._handle_v3_autofocus_state_notification(packet)
        elif command_id == protocol_pb2.DwarfCMD.CMD_NOTIFY_LONG_EXP_PROGRESS:
            self._handle_long_exposure_progress_notification(packet)
        elif command_id == _CMD_NOTIFY_CMOS_TEMPERATURE:
            self._handle_v3_temperature2_notification(packet)
        elif command_id == _CMD_NOTIFY_SKY_TARGET_FINDER_STATE:
            self._handle_v3_observation_state_notification(packet)
        elif command_id == protocol_pb2.DwarfCMD.CMD_NOTIFY_ELE:
            self._handle_battery_notification(packet)

    @staticmethod
    def _enum_name(enum_wrapper: Any, value: int) -> str:
        try:
            return str(enum_wrapper.Name(value))
        except (KeyError, ValueError):
            return "UNKNOWN"

    def _trace_calibration_notification(self, packet: Message) -> None:
        started = self._calibration_trace_started
        if started is None:
            return
        self._calibration_trace_notifications += 1
        module_id = int(getattr(packet, "module_id", 0))
        command_id = int(getattr(packet, "cmd", 0))
        packet_type = int(getattr(packet, "type", 0))
        raw_data = bytes(getattr(packet, "data", b"") or b"")
        logged_data = raw_data[:512]
        logger.info(
            "dwarf.telescope.calibration.trace.notification",
            sequence=self._calibration_trace_notifications,
            elapsed_seconds=round(time.monotonic() - started, 3),
            module_id=module_id,
            module_name=self._enum_name(protocol_pb2.ModuleId, module_id),
            command_id=command_id,
            command_name=self._enum_name(protocol_pb2.DwarfCMD, command_id),
            packet_type=packet_type,
            payload_length=len(raw_data),
            payload_hex=logged_data.hex(),
            payload_truncated=len(logged_data) != len(raw_data),
        )

    def _begin_calibration_trace(self, *, latitude: float, longitude: float) -> None:
        self._calibration_trace_started = time.monotonic()
        self._calibration_trace_last_state = None
        self._calibration_trace_notifications = 0
        logger.info(
            "dwarf.telescope.calibration.trace.started",
            latitude=latitude,
            longitude=longitude,
        )

    def _finish_calibration_trace(
        self, *, outcome: str, error: BaseException | None = None
    ) -> None:
        started = self._calibration_trace_started
        if started is None:
            return
        logger.info(
            "dwarf.telescope.calibration.trace.finished",
            outcome=outcome,
            elapsed_seconds=round(time.monotonic() - started, 3),
            notification_count=self._calibration_trace_notifications,
            final_status=self._calibration_status,
            final_detail=self._calibration_detail,
            error=None if error is None else str(error),
            error_type=None if error is None else type(error).__name__,
        )
        self._calibration_trace_started = None
        self._calibration_trace_last_state = None

    def _handle_calibration_state_notification(self, packet: Message) -> None:
        raw_data = getattr(packet, "data", b"") or b""
        if not raw_data:
            logger.warning("dwarf.telescope.calibration.notification.empty", command_id=15210)
            return
        message = AstroCalibrationState()
        try:
            message.ParseFromString(raw_data)
        except Exception as exc:  # pragma: no cover - defensive logging helper
            logger.warning(
                "dwarf.telescope.calibration.notification.decode_failed",
                command_id=15210,
                payload_hex=raw_data.hex(),
                error=str(exc),
            )
            return
        state_value = int(message.state)
        state_name = {
            0: "idle",
            1: "running",
            2: "stopping",
            3: "stopped",
            4: "plate solving",
        }.get(state_value, "unknown")
        plate_solving_times = int(message.plate_solving_times)
        now = time.monotonic()
        started = self._calibration_trace_started
        previous_state = self._calibration_trace_last_state
        self._calibration_trace_last_state = now
        self._calibration_status = state_name
        self._calibration_detail = (
            f"Plate solving attempt {plate_solving_times}"
            if state_name == "plate solving" and plate_solving_times > 0
            else None
        )
        logger.info(
            "dwarf.telescope.calibration.notification.state",
            state=state_name.replace(" ", "_"),
            state_value=state_value,
            plate_solving_times=plate_solving_times,
            elapsed_seconds=(None if started is None else round(now - started, 3)),
            since_previous_state_seconds=(
                None if previous_state is None else round(now - previous_state, 3)
            ),
            payload_hex=raw_data.hex(),
        )

    def _handle_calibration_result_notification(self, packet: Message) -> None:
        raw_data = getattr(packet, "data", b"") or b""
        if not raw_data:
            logger.warning("dwarf.telescope.calibration.result.empty", command_id=15256)
            return
        message = CalibrationResult()
        try:
            message.ParseFromString(raw_data)
        except Exception as exc:  # pragma: no cover - defensive logging helper
            logger.warning(
                "dwarf.telescope.calibration.result.decode_failed",
                command_id=15256,
                payload_hex=raw_data.hex(),
                error=str(exc),
            )
            return
        self._calibration_azimuth = float(message.azi)
        self._calibration_altitude = float(message.alt)
        self._calibration_status = "successful"
        self._calibration_detail = (
            f"Azimuth {self._calibration_azimuth:.2f}\N{DEGREE SIGN}, "
            f"altitude {self._calibration_altitude:.2f}\N{DEGREE SIGN}"
        )
        self._calibration_result_event.set()
        self._last_calibration_time = time.time()
        self._last_calibration_ip = self.settings.dwarf_ap_ip
        logger.info(
            "dwarf.telescope.calibration.notification.result",
            outcome="successful",
            azimuth=self._calibration_azimuth,
            altitude=self._calibration_altitude,
            payload_hex=raw_data.hex(),
        )
        self._finish_calibration_trace(outcome="successful")

    def _handle_battery_notification(self, packet: Message) -> None:
        raw_data = getattr(packet, "data", b"") or b""
        if not raw_data:
            return
        value = _decode_com_res_with_int_value(raw_data)
        if value is None:
            logger.debug("dwarf.battery.notification.decode_failed")
            return
        try:
            percent = int(value)
        except (TypeError, ValueError):
            return
        percent = max(0, min(100, percent))
        state = self.camera_state
        if state.battery_percent != percent:
            logger.info("dwarf.battery.notification", battery_percent=percent)
        state.battery_percent = percent
        state.last_battery_time = time.time()

    def _handle_feature_param_notification(self, packet: Message) -> None:
        # Feature-param notifications are not Mini filter-wheel readback.
        # App 3.4.1 carries the Mini filter only in the astronomy start request.
        return

    def _set_astro_capture_operation_state(self, value: int, *, source: str) -> None:
        try:
            operation_state = _OperationState(value)
            state_name = operation_state.name.lower()
        except ValueError:
            operation_state = None
            state_name = "unknown"
        self._astro_capture_operation_state = int(value)
        ready = operation_state in {_OperationState.IDLE, _OperationState.STOPPED}
        if ready:
            self._astro_capture_ready_event.set()
        else:
            self._astro_capture_ready_event.clear()
        logger.info(
            "dwarf.camera.astro_capture_state",
            state=int(value),
            state_name=state_name,
            ready=ready,
            source=source,
        )

    def _handle_astro_capture_state_notification(self, packet: Message) -> None:
        raw_data = bytes(getattr(packet, "data", b"") or b"")
        # Protobuf omits the field for enum value zero, so an empty payload is
        # the valid IDLE notification seen immediately before a new capture.
        value = 0 if not raw_data else _decode_com_res_with_int_value(raw_data)
        if value is None:
            logger.warning(
                "dwarf.camera.astro_capture_state_decode_failed",
                payload_hex=raw_data.hex(),
            )
            return
        self._set_astro_capture_operation_state(value, source="notification_15208")

    def _handle_astro_capture_progress_notification(self, packet: Message) -> None:
        raw_data = getattr(packet, "data", b"") or b""
        if not raw_data:
            return
        message = ProgressCaptureRawLiveStacking()
        try:
            message.ParseFromString(raw_data)
        except Exception as exc:  # pragma: no cover - defensive logging helper
            logger.warning(
                "dwarf.camera.astro_capture_progress_decode_failed",
                payload_hex=raw_data.hex(),
                error=str(exc),
            )
            return

        state = self.camera_state
        total_count = int(message.total_count)
        current_count = int(message.current_count)
        update_type = int(message.update_type)
        camera_type = int(message.camera_type)
        shooting_time = int(message.shooting_time) if message.HasField("shooting_time") else None
        stacked_time = int(message.stacked_time) if message.HasField("stacked_time") else None

        if total_count > 0:
            state.progress_total_count = total_count
        if current_count > 0:
            state.progress_current_count = max(state.progress_current_count, current_count)
        requested_frames = max(1, int(state.requested_frame_count or 1))
        raw_frames_ready = state.progress_current_count >= requested_frames
        completed = raw_frames_ready
        logger.info(
            "dwarf.camera.astro_capture_progress",
            capture_id=state.capture_id,
            total_count=state.progress_total_count,
            current_count=state.progress_current_count,
            update_type=update_type,
            camera_type=camera_type,
            shooting_time=shooting_time,
            stacked_time=stacked_time,
            requested_frames=requested_frames,
            raw_frames_ready=raw_frames_ready,
            completed=completed,
        )
        self._capture_start_evidence_event.set()
        if completed and state.capture_id is not None:
            self._capture_frame_complete_event.set()

    def _handle_v3_camera_param_state_notification(self, packet: Message) -> None:
        raw_data = bytes(getattr(packet, "data", b"") or b"")
        if not raw_data:
            return
        message = GeneralIntParam()
        try:
            message.ParseFromString(raw_data)
        except Exception as exc:  # pragma: no cover - defensive logging helper
            logger.debug("dwarf.camera.general_int_param_decode_failed", error=str(exc))
            return
        param_id = int(message.param_id)
        param_mode_id = (param_id >> _V3_PARAM_MODE_SHIFT) & 0xFF
        param_key = param_id & _V3_PARAM_MODE_VALUE_MASK
        exposure_key = _V3_ASTRO_EXPOSURE_PARAM_ID & _V3_PARAM_MODE_VALUE_MASK
        gain_key = _V3_ASTRO_GAIN_PARAM_ID & _V3_PARAM_MODE_VALUE_MASK
        state = self.camera_state
        if (
            state.capture_id is not None
            and state.capture_phase
            in {CapturePhase.STARTING, CapturePhase.EXPOSING}
            and param_mode_id != _V3_ASTRO_MODE_ID
            and param_key in {exposure_key, gain_key}
        ):
            if self._v3_capture_param_mode_id != param_mode_id:
                self._v3_capture_param_mode_id = param_mode_id
                logger.info(
                    "dwarf.camera.v3_capture_param_namespace_detected",
                    capture_id=state.capture_id,
                    mode_id=param_mode_id,
                    param_id=param_id,
                )
        logger.debug(
            "dwarf.camera.general_int_param",
            param_id=param_id,
            mode=int(message.mode),
            value=int(message.value),
        )

    def _handle_v3_exposure_progress_notification(self, packet: Message) -> None:
        raw_data = getattr(packet, "data", b"") or b""
        if not raw_data:
            return
        message = V3ResNotifyExposureProgress()
        try:
            message.ParseFromString(raw_data)
        except Exception as exc:  # pragma: no cover - defensive logging helper
            logger.debug("dwarf.camera.v3_exposure_progress_decode_failed", error=str(exc))
            return
        try:
            elapsed = int(getattr(message, "elapsed", 0))
            total = int(getattr(message, "total", 0))
        except (TypeError, ValueError):
            return
        self._v3_exposure_progress = (elapsed, total)
        self._capture_start_evidence_event.set()
        state = self.camera_state
        capture_id = state.capture_id
        # DWARF 3 can reload its internal capture preset near the end of the
        # wait-shooting preparation. When elapsed=7 is emitted, it follows that
        # reload and precedes 15288 starting the sensor exposure, so it is a
        # useful final checkpoint for reapplying exact live values.
        should_reapply = (
            elapsed >= 7
            and capture_id is not None
            and self._v3_live_parameters_supported is not False
            and self._v3_runtime_reapply_capture_id != capture_id
            and state.capture_phase
            in {
                CapturePhase.STARTING,
                CapturePhase.EXPOSING,
                CapturePhase.PROCESSING,
            }
        )
        if elapsed >= 7:
            logger.info(
                "dwarf.camera.v3_capture_runtime_reapply_checkpoint",
                capture_id=capture_id,
                capture_phase=state.capture_phase.value,
                detected_mode_id=self._v3_capture_param_mode_id,
                elapsed=elapsed,
                live_parameters_supported=self._v3_live_parameters_supported,
                scheduled=should_reapply,
                total=total,
            )
        if should_reapply:
            self._v3_runtime_reapply_capture_id = capture_id
            asyncio.create_task(
                self._reapply_v3_capture_runtime_parameters(capture_id),
                name=f"dwarf-v3-runtime-params-{capture_id}",
            )

    async def _reapply_v3_capture_runtime_parameters(self, capture_id: str) -> None:
        state = self.camera_state
        try:
            requested_gain = state.requested_gain
            if requested_gain is None:
                requested_gain = int(self.profile.camera.min_gain_db)
            await self._apply_v3_capture_runtime_parameters(
                state.duration,
                int(requested_gain),
                max(1, int(state.requested_frame_count)),
                mode_id=self._v3_capture_param_mode_id,
            )
            logger.info(
                "dwarf.camera.v3_capture_runtime_params_reapplied",
                capture_id=capture_id,
                trigger="wait_shooting_progress",
            )
        except Exception as exc:
            logger.warning(
                "dwarf.camera.v3_capture_runtime_params_reapply_failed",
                capture_id=capture_id,
                error=str(exc),
                error_type=type(exc).__name__,
            )

    def _handle_long_exposure_progress_notification(self, packet: Message) -> None:
        raw_data = bytes(getattr(packet, "data", b"") or b"")
        if not raw_data:
            return
        message = LongExpPhotoProgress()
        try:
            message.ParseFromString(raw_data)
        except Exception as exc:  # pragma: no cover - defensive logging helper
            logger.debug("dwarf.camera.long_exposure_progress_decode_failed", error=str(exc))
            return
        total_time = float(message.total_time)
        state = self.camera_state
        if state.capture_id is not None and state.capture_phase in {
            CapturePhase.STARTING,
            CapturePhase.EXPOSING,
            CapturePhase.PROCESSING,
            CapturePhase.TRANSFERRING,
        } and total_time > 0:
            state.reported_duration = total_time
            # This notification is the firmware's authoritative duration.
            # Preserve the requested duration in ``state.duration`` for
            # diagnostics, but expose the actual value through the Alpaca
            # LastExposureDuration property.
            state.applied_duration = total_time
            tolerance = max(0.001, state.duration * 0.02)
            if not math.isclose(total_time, state.duration, abs_tol=tolerance):
                logger.warning(
                    "dwarf.camera.exposure_duration_mismatch",
                    capture_id=state.capture_id,
                    requested_duration=state.duration,
                    firmware_duration=total_time,
                )
        logger.info(
            "dwarf.camera.long_exposure_progress",
            total_time=total_time,
            exposed_time=float(message.exposured_time),
            camera_type=int(message.camera_type),
        )

    def _handle_v3_device_state_notification(self, packet: Message) -> None:
        raw_data = getattr(packet, "data", b"") or b""
        if not raw_data:
            return
        message = ResNotifyTaskState()
        try:
            message.ParseFromString(raw_data)
        except Exception as exc:  # pragma: no cover - defensive logging helper
            logger.debug("dwarf.system.v3_device_state_decode_failed", error=str(exc))
            return

        self._v3_device_state_event = int(message.task_id)
        self._v3_device_state_mode = int(message.task_attr.exclusive_mask)
        self._v3_device_state_detail = int(message.state.base_state)
        self._v3_device_state_path = None
        logger.info(
            "dwarf.system.task_state",
            task_id=int(message.task_id),
            exclusive_mask=int(message.task_attr.exclusive_mask),
            priority=int(message.task_attr.priority),
            base_state=int(message.state.base_state),
            astro_extended_state=int(message.state.astro_extended_state),
        )

    def _handle_v3_mode_change_notification(self, packet: Message) -> None:
        raw_data = getattr(packet, "data", b"") or b""
        if not raw_data:
            return
        message = SwitchShootingMode()
        try:
            message.ParseFromString(raw_data)
        except Exception as exc:  # pragma: no cover - defensive logging helper
            logger.debug("dwarf.system.v3_mode_change_decode_failed", error=str(exc))
            return
        try:
            state = int(message.state)
            source_mode = int(message.source_mode)
            destination_mode = int(message.dst_mode)
        except (TypeError, ValueError):
            return
        self._v3_mode_change = (state, source_mode, destination_mode)
        self._v3_device_state_mode = destination_mode

    def _handle_v3_autofocus_state_notification(self, packet: Message) -> None:
        raw_data = getattr(packet, "data", b"") or b""
        if not raw_data:
            logger.warning("dwarf.focus.autofocus.notification.empty")
            return
        message_cls = (
            AstroAutoFocusFastState
            if int(getattr(packet, "cmd", 0))
            == int(protocol_pb2.DwarfCMD.CMD_NOTIFY_ASTRO_AUTO_FOCUS_FAST_STATE)
            else AstroAutoFocusState
        )
        message = message_cls()
        try:
            message.ParseFromString(raw_data)
        except Exception as exc:  # pragma: no cover - defensive logging helper
            logger.warning(
                "dwarf.focus.autofocus.notification.decode_failed",
                command_id=getattr(packet, "cmd", None),
                payload_hex=raw_data.hex(),
                error=str(exc),
            )
            return
        state_value = int(message.state)
        state_name = {1: "running", 3: "completed"}.get(state_value, "unknown")
        if state_value == 1:
            self._calibration_status = "autofocusing"
            self._calibration_detail = "Astronomical autofocus is running"
        elif state_value == 3:
            self._calibration_status = "autofocus completed"
            self._calibration_detail = "Starting mount calibration"
            self._autofocus_completion_event.set()
        logger.info(
            "dwarf.focus.autofocus.notification.state",
            command_id=getattr(packet, "cmd", None),
            state=state_name,
            state_value=state_value,
            payload_hex=raw_data.hex(),
        )

    def _handle_v3_temperature2_notification(self, packet: Message) -> None:
        raw_data = getattr(packet, "data", b"") or b""
        if not raw_data:
            return
        message = CmosTemperature()
        try:
            message.ParseFromString(raw_data)
        except Exception as exc:  # pragma: no cover - defensive logging helper
            logger.debug("dwarf.camera.v3_temperature2_decode_failed", error=str(exc))
            return
        if not message.HasField("temperature"):
            return
        self.camera_state.temperature_c = float(message.temperature)
        self.camera_state.last_temperature_time = time.time()
        # V3 temperature2 notification does not include a response code.
        self.camera_state.last_temperature_code = protocol_pb2.OK

    def _handle_v3_observation_state_notification(self, packet: Message) -> None:
        raw_data = getattr(packet, "data", b"") or b""
        if not raw_data:
            return
        message = SkyTargetFinderState()
        try:
            message.ParseFromString(raw_data)
        except Exception as exc:  # pragma: no cover - defensive logging helper
            logger.debug("dwarf.astro.v3_observation_state_decode_failed", error=str(exc))
            return
        try:
            self._v3_observation_state = int(message.state)
        except (TypeError, ValueError):
            return
        logger.info(
            "dwarf.astro.sky_target_finder_state",
            state=self._v3_observation_state,
            scene_type=int(message.scene_type),
        )

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
        position = max(0, min(int(message.pos), 20000))
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

    def _handle_goto_state_notification(self, packet: Message) -> None:
        if self.simulation:
            return
        if not self._goto_pending or self._last_goto_kind != _GOTO_KIND_DSO:
            return
        raw_data = getattr(packet, "data", b"") or b""
        if not raw_data:
            return
        message = ResNotifyStateAstroGoto()
        try:
            message.ParseFromString(raw_data)
        except Exception as exc:  # pragma: no cover - defensive logging helper
            logger.debug(
                "dwarf.goto.notification.decode_failed",
                error=str(exc),
            )
            return
        state_value = getattr(message, "state", None)
        if state_value is None:
            return
        try:
            state = _AstroState(int(state_value))
        except ValueError:
            logger.debug(
                "dwarf.goto.notification.unknown_state",
                state_value=state_value,
            )
            return
        logger.debug(
            "dwarf.goto.notification.state",
            state=state.name,
            state_value=state_value,
        )
        if state in (_AstroState.RUNNING, _AstroState.PLATE_SOLVING, _AstroState.STOPPING):
            self._goto_waiting_for_tracking = True
        elif state == _AstroState.IDLE and self._goto_waiting_for_tracking:
            self._resolve_goto("failed", reason="goto_idle", keep_record=False)

    def _handle_one_click_goto_state_notification(self, packet: Message) -> None:
        raw_data = getattr(packet, "data", b"") or b""
        if not raw_data:
            logger.warning("dwarf.goto.one_click.notification.empty", command_id=15233)
            return
        message = OneClickGotoState()
        try:
            message.ParseFromString(raw_data)
        except Exception as exc:  # pragma: no cover - defensive logging helper
            logger.warning(
                "dwarf.goto.one_click.notification.decode_failed",
                command_id=15233,
                payload_hex=raw_data.hex(),
                error=str(exc),
            )
            return
        current_state = message.WhichOneof("current_state")
        if current_state is None:
            logger.warning(
                "dwarf.goto.one_click.notification.missing_state",
                payload_hex=raw_data.hex(),
            )
            return
        phase = {
            "astro_auto_focus_state": "autofocus",
            "astro_calibration_state": "calibration",
            "astro_goto_state": "goto",
            "astro_tracking_state": "tracking",
        }[current_state]
        phase_state = getattr(message, current_state)
        state_value = int(phase_state.state)
        target_name = self._goto_target_name
        if current_state in {"astro_goto_state", "astro_tracking_state"}:
            target_name = str(phase_state.target_name).strip() or target_name

        state_name = {
            0: "idle",
            1: "running",
            2: "stopping",
            3: "stopped",
            4: "plate_solving",
        }.get(state_value, "unknown")
        logger.info(
            "dwarf.goto.one_click.notification.state",
            phase=phase,
            state=state_name,
            state_value=state_value,
            target_name=target_name,
            payload_hex=raw_data.hex(),
        )
        if not self._goto_pending or not self._one_click_goto_active:
            return
        if phase in {"autofocus", "calibration", "goto"} and state_value in {1, 2, 3, 4}:
            self._goto_waiting_for_tracking = True
        if phase == "tracking" and state_value == 1:
            reason = "one_click_tracking_running"
            if target_name:
                reason = f"one_click_tracking_running:{target_name}"
            self._resolve_goto("success", reason=reason, keep_record=True)

    def _handle_tracking_state_notification(self, packet: Message) -> None:
        if self.simulation:
            return
        raw_data = getattr(packet, "data", b"") or b""
        if not raw_data:
            return
        message = ResNotifyStateAstroTracking()
        try:
            message.ParseFromString(raw_data)
        except Exception as exc:  # pragma: no cover - defensive logging helper
            logger.debug(
                "dwarf.tracking.notification.decode_failed",
                error=str(exc),
            )
            return
        state_value = getattr(message, "state", None)
        if state_value is None:
            return
        try:
            state = _OperationState(int(state_value))
        except ValueError:
            logger.debug(
                "dwarf.tracking.notification.unknown_state",
                state_value=state_value,
            )
            return
        target_name = getattr(message, "target_name", "") or None
        logger.debug(
            "dwarf.tracking.notification.state",
            state=state.name,
            state_value=state_value,
            target_name=target_name,
        )
        if not self._goto_pending or self._last_goto_kind != _GOTO_KIND_DSO:
            return
        if state == _OperationState.RUNNING:
            reason = "tracking_running"
            if target_name:
                reason = f"tracking_running:{target_name}"
            self._resolve_goto("success", reason=reason, keep_record=True)
        elif (
            state in (_OperationState.STOPPED, _OperationState.IDLE)
            and self._goto_waiting_for_tracking
        ):
            reason = "tracking_not_running"
            if target_name:
                reason = f"tracking_not_running:{target_name}"
            self._resolve_goto("failed", reason=reason, keep_record=False)

    def _ensure_temperature_monitor_task(self) -> None:
        task = self._temperature_task
        if task and task.done():
            with contextlib.suppress(asyncio.CancelledError, Exception):
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

                if (
                    not self.simulation
                    and self._ws_client.connected
                    and self.camera_state.connected
                ):
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
        if self._uses_v3_protocol():
            return
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
        suppress_timeout_warning: bool = False,
        close_ws_on_timeout: bool = True,
    ) -> Message:
        lock = self._get_ws_command_lock()
        async with lock:
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
            try:
                response = await send_and_check(
                    self._ws_client,
                    module_id,
                    command_id,
                    request,
                    timeout=timeout,
                    expected_responses=expected_responses,
                )
            except asyncio.TimeoutError as exc:
                await self._handle_ws_timeout_with_options(
                    module_id,
                    command_id,
                    exc,
                    log_as_warning=not suppress_timeout_warning,
                    close_ws=close_ws_on_timeout,
                )
                raise
            logger.info(
                "dwarf.ws.command.send_and_check.completed",
                module_id=module_id,
                command_id=command_id,
            )
            return response

    async def _send_request(
        self,
        module_id: int,
        command_id: int,
        request: Message,
        response_cls: Type[Message],
        *,
        timeout: float = 10.0,
        expected_responses: Optional[Dict[Tuple[int, int], Type[Message]]] = None,
        suppress_timeout_warning: bool = False,
        close_ws_on_timeout: bool = True,
    ) -> Message:
        lock = self._get_ws_command_lock()
        async with lock:
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
            try:
                response = await self._ws_client.send_request(
                    module_id,
                    command_id,
                    request,
                    response_cls,
                    timeout=timeout,
                    expected_responses=expected_responses,
                )
            except asyncio.TimeoutError as exc:
                await self._handle_ws_timeout_with_options(
                    module_id,
                    command_id,
                    exc,
                    log_as_warning=not suppress_timeout_warning,
                    close_ws=close_ws_on_timeout,
                )
                raise
            logger.info(
                "dwarf.ws.command.response",
                module_id=module_id,
                command_id=command_id,
                response_type=response.__class__.__name__,
                response_payload=_message_to_log(response),
                response_code=getattr(response, "code", None),
            )
            return response

    async def _begin_request(
        self,
        module_id: int,
        command_id: int,
        request: Message,
        response_cls: Type[Message],
    ) -> asyncio.Future[Message]:
        """Send a long-running request without blocking on its final response."""

        lock = self._get_ws_command_lock()
        async with lock:
            logger.info(
                "dwarf.ws.command.begin",
                module_id=module_id,
                command_id=command_id,
                request_type=request.__class__.__name__,
                request_payload=_message_to_log(request),
                expected_response_type=response_cls.__name__,
            )
            return await self._ws_client.begin_request(
                module_id,
                command_id,
                request,
                response_cls,
            )

    async def _send_command(
        self,
        module_id: int,
        command_id: int,
        request: Message,
        *,
        timeout: float = 10.0,
        expected_responses: Optional[Dict[Tuple[int, int], Type[Message]]] = None,
        suppress_timeout_warning: bool = False,
        close_ws_on_timeout: bool = True,
    ) -> Message:
        return await self._send_request(
            module_id,
            command_id,
            request,
            ComResponse,
            timeout=timeout,
            expected_responses=expected_responses,
            suppress_timeout_warning=suppress_timeout_warning,
            close_ws_on_timeout=close_ws_on_timeout,
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
                    protocol_pb2.DwarfCMD.CMD_SYSTEM_SET_MASTER,
                    request,
                    ComResponse,
                    timeout=15.0,
                    expected_responses=expected_responses,
                )

                if isinstance(response, ComResponse):
                    if response.code != protocol_pb2.OK:
                        raise DwarfCommandError(
                            protocol_pb2.ModuleId.MODULE_SYSTEM,
                            protocol_pb2.DwarfCMD.CMD_SYSTEM_SET_MASTER,
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

                if self._master_lock_acquired and self._uses_v3_protocol():
                    await self._bootstrap_v3_state()
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
                    protocol_pb2.DwarfCMD.CMD_SYSTEM_SET_MASTER,
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

        if self.simulation:
            return

        timezone_label, offset_hours, offset_source = self._determine_timezone_details()
        timezone_offset = round(offset_hours * 4.0) / 4.0

        if self._time_synced and self._last_time_sync_offset == timezone_offset:
            if timezone_label == self._last_time_sync_timezone:
                return

        request = ReqSetTime()
        timestamp_utc = math.floor(time.time())
        request.timestamp = timestamp_utc
        request.timezone_offset = timezone_offset
        local_timestamp = timestamp_utc + int(round(timezone_offset * 3600.0))

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
                timestamp=timestamp_utc,
                timezone_offset=timezone_offset,
                offset_raw=offset_hours,
                offset_source=offset_source,
                timestamp_local=local_timestamp,
                timezone_label=timezone_label,
            )
            return

        if (
            timezone_label
            and "/" in timezone_label
            and timezone_label != self._last_time_sync_timezone
        ):
            tz_request = ReqSetTimezone()
            tz_request.timezone = timezone_label
            try:
                await self._send_and_check(
                    protocol_pb2.ModuleId.MODULE_SYSTEM,
                    protocol_pb2.DwarfCMD.CMD_SYSTEM_SET_TIME_ZONE,
                    tz_request,
                    timeout=5.0,
                )
            except Exception as exc:  # pragma: no cover - hardware dependent
                logger.warning(
                    "dwarf.system.timezone_sync_failed",
                    error=str(exc),
                    timezone=timezone_label,
                    timezone_offset=timezone_offset,
                    offset_source=offset_source,
                )
            else:
                self._last_time_sync_timezone = timezone_label
                logger.info(
                    "dwarf.system.timezone_synced",
                    timezone=timezone_label,
                    timezone_offset=timezone_offset,
                    offset_source=offset_source,
                )
        else:
            self._last_time_sync_timezone = timezone_label

        self._time_synced = True
        self._last_time_sync_offset = timezone_offset
        logger.info(
            "dwarf.system.time_synced",
            timestamp=timestamp_utc,
            timezone_offset=timezone_offset,
            offset_raw=offset_hours,
            offset_source=offset_source,
            timestamp_utc=timestamp_utc,
            timestamp_local=local_timestamp,
            timezone_label=timezone_label or self._format_timezone_label(offset_hours),
        )

    def _determine_timezone_details(self) -> tuple[str | None, float, str]:
        configured_name = self._normalize_timezone_name(self.settings.timezone_name)
        if configured_name:
            offset = self._timezone_offset_for_label(configured_name)
            if offset is not None:
                return configured_name, offset, "configured"
            logger.warning(
                "dwarf.system.timezone_invalid",
                timezone=configured_name,
            )

        system_label, system_offset = self._system_timezone_details()
        return system_label, system_offset, "system"

    @staticmethod
    def _normalize_timezone_name(value: Optional[str]) -> str | None:
        if isinstance(value, str):
            normalized = value.strip()
            if normalized:
                return normalized
        return None

    def _timezone_offset_for_label(self, label: str) -> float | None:
        if ZoneInfo is None:
            return None
        try:
            zone = ZoneInfo(label)
        except Exception:
            return None
        now = datetime.now(tz=zone)
        offset = now.utcoffset()
        if offset is None:
            return None
        return offset.total_seconds() / 3600.0

    @staticmethod
    def _system_timezone_details() -> tuple[str | None, float]:
        local_dt = datetime.now().astimezone()
        offset = local_dt.utcoffset()
        offset_hours = offset.total_seconds() / 3600.0 if offset else 0.0
        tzinfo = local_dt.tzinfo
        label: str | None = None
        if tzinfo is not None:
            candidate = getattr(tzinfo, "key", None) or getattr(tzinfo, "zone", None)
            if isinstance(candidate, str) and "/" in candidate:
                label = candidate.strip() or None
        return label, offset_hours

    @staticmethod
    def _format_timezone_label(offset_hours: float) -> str:
        offset_seconds = int(round(offset_hours * 3600.0))
        if offset_seconds == 0:
            return "UTC"
        sign = "+" if offset_seconds >= 0 else "-"
        offset_seconds = abs(offset_seconds)
        hours, remainder = divmod(offset_seconds, 3600)
        minutes = remainder // 60
        return f"UTC{sign}{hours:02d}:{minutes:02d}"

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
                await self._cancel_capture_protocol_tasks()
                task = self._calibration_task
                if task and not task.done():
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        await task
                self._calibration_task = None
                # Closing the socket alone can leave DWARF 3 reporting
                # DEVICE_OCCUPIED while the GUI hands control from its
                # preflight loop to the embedded server loop. Relinquish the
                # firmware master lock explicitly before closing transport.
                await self._release_master_lock()
                await self._ws_client.close()
                await self._http_client.aclose()

    async def shutdown(self) -> None:
        if self.camera_state.capture_task and not self.camera_state.capture_task.done():
            self.camera_state.capture_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.camera_state.capture_task
        self.camera_state.capture_task = None

        await self._cancel_capture_protocol_tasks()

        temperature_task = self._temperature_task
        if temperature_task:
            temperature_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await temperature_task
            self._temperature_task = None

        task = self._calibration_task
        if task and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        self._calibration_task = None

        one_click_task = self._one_click_response_task
        if one_click_task and not one_click_task.done():
            one_click_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await one_click_task
        self._one_click_response_task = None

        await self._release_master_lock()

        if not self.simulation:
            await self._ws_client.close()
            await self._http_client.aclose()

        self._master_lock_acquired = False
        self._ws_bootstrapped = False
        for key in self._refs:
            self._refs[key] = 0
        self._last_calibration_time = None
        self._last_calibration_ip = None

    async def _cancel_capture_protocol_tasks(self) -> None:
        """Cancel delayed V3 start/stop response monitors before closing the socket."""

        for attribute in ("_capture_start_response_task", "_capture_stop_response_task"):
            task = getattr(self, attribute)
            if task and not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
            setattr(self, attribute, None)
        cancel_pending = getattr(self._ws_client, "cancel_pending", None)
        if callable(cancel_pending):
            cancel_pending(
                protocol_pb2.ModuleId.MODULE_ASTRO,
                protocol_pb2.DwarfCMD.CMD_ASTRO_START_CAPTURE_RAW_LIVE_STACKING,
            )
            cancel_pending(
                protocol_pb2.ModuleId.MODULE_ASTRO,
                protocol_pb2.DwarfCMD.CMD_ASTRO_STOP_CAPTURE_RAW_LIVE_STACKING,
            )

    # --- Telescope -----------------------------------------------------------------

    async def telescope_slew_to_coordinates(
        self,
        ra_hours: float,
        dec_degrees: float,
        *,
        target_name: str = "Custom",
    ) -> tuple[float, float]:
        if not target_name or target_name.casefold() == "custom":
            resolved_target = resolve_nina_target_name(ra_hours, dec_degrees)
            if resolved_target:
                logger.info(
                    "dwarf.telescope.target_name_resolved",
                    requested_name=target_name,
                    resolved_name=resolved_target,
                    ra_hours=ra_hours,
                    dec_degrees=dec_degrees,
                )
                target_name = resolved_target
        if self.simulation:
            self._record_goto(ra_hours, dec_degrees)
            return ra_hours, dec_degrees

        await self._ensure_ws()
        await self._halt_manual_motion()
        use_one_click_goto = (
            self.settings.auto_calibrate_on_slew and not self._has_recent_calibration()
        )
        if use_one_click_goto:
            await self._prepare_calibration_autofocus()
            await self._prepare_one_click_goto_mode()
        try:
            if use_one_click_goto:
                await self._start_one_click_goto_command(
                    ra_hours, dec_degrees, target_name
                )
            else:
                await self._start_goto_command(ra_hours, dec_degrees, target_name)
        except DwarfCommandError as exc:
            pending_error: DwarfCommandError | None = exc
            if (
                exc.code == protocol_pb2.CODE_ASTRO_NEED_CALIBRATION
                and not use_one_click_goto
                and self.settings.auto_calibrate_on_slew
            ):
                logger.warning(
                    "dwarf.telescope.goto.calibration_required",
                    ra_hours=ra_hours,
                    dec_degrees=dec_degrees,
                    code=exc.code,
                    fallback="one_click_goto",
                )
                self._last_calibration_time = None
                self._last_calibration_ip = None
                await self._prepare_calibration_autofocus()
                await self._prepare_one_click_goto_mode()
                use_one_click_goto = True
                try:
                    await self._start_one_click_goto_command(
                        ra_hours, dec_degrees, target_name
                    )
                except DwarfCommandError as fallback_error:
                    pending_error = fallback_error
                else:
                    pending_error = None

            if pending_error is None:
                return ra_hours, dec_degrees
            retryable_codes = {
                protocol_pb2.CODE_ASTRO_FUNCTION_BUSY,
                protocol_pb2.CODE_ASTRO_GOTO_FAILED,
            }
            if pending_error.code not in retryable_codes:
                raise pending_error
            logger.warning(
                "dwarf.telescope.goto.retrying",
                ra_hours=ra_hours,
                dec_degrees=dec_degrees,
                code=pending_error.code,
                one_click=use_one_click_goto,
            )
            await self.telescope_abort_slew()
            await asyncio.sleep(0.2)
            await self._halt_manual_motion()
            if use_one_click_goto:
                await self._start_one_click_goto_command(
                    ra_hours, dec_degrees, target_name
                )
            else:
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
        # Firmware defines vector_length as the 0..1 joystick speed scale. The
        # former field-3 speed value doesn't exist in the descriptor and was
        # ignored by current firmware.
        vector_length = min(1.0, speed / _MAX_JOYSTICK_SPEED)
        angle = math.degrees(math.atan2(rate_y, rate_x))
        if angle < 0.0:
            angle += 360.0

        request = ReqMotorServiceJoystick()
        request.vector_angle = angle
        request.vector_length = vector_length

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

    def _record_goto(
        self, ra_hours: float, dec_degrees: float, *, kind: str = _GOTO_KIND_DSO
    ) -> None:
        self._last_goto_time = time.time()
        self._last_goto_target = (ra_hours, dec_degrees)
        self._last_goto_kind = kind
        logger.debug(
            "dwarf.telescope.goto_recorded",
            ra_hours=ra_hours,
            dec_degrees=dec_degrees,
        )

    def _drop_goto_record(self) -> None:
        self._last_goto_time = None
        self._last_goto_target = None
        self._last_goto_kind = None
        self._goto_target_name = None

    def _mark_goto_pending(self, *, kind: str, target_name: str | None) -> None:
        if self._goto_pending:
            self._resolve_goto("superseded", reason="new_goto_started", keep_record=False)
        self._goto_pending = True
        self._goto_waiting_for_tracking = (kind == _GOTO_KIND_DSO) and not self.simulation
        self._goto_result = None
        self._goto_reason = None
        self._goto_target_name = target_name or None
        self._goto_start_time = time.time()
        self._goto_completion_event.clear()
        logger.info(
            "dwarf.telescope.goto.pending",
            kind=kind,
            target_name=self._goto_target_name,
        )

    def _resolve_goto(self, result: str, *, reason: str | None = None, keep_record: bool) -> None:
        if not self._goto_pending and result not in {"success", "simulation"}:
            return
        duration = None
        if self._goto_start_time is not None:
            duration = time.time() - self._goto_start_time
        self._goto_pending = False
        self._goto_waiting_for_tracking = False
        self._one_click_goto_active = False
        self._goto_result = result
        self._goto_reason = reason
        self._goto_start_time = None
        if keep_record:
            self._last_goto_time = time.time()
        else:
            self._drop_goto_record()
        self._goto_completion_event.set()
        logger.info(
            "dwarf.telescope.goto.resolved",
            result=result,
            reason=reason,
            duration=duration,
            target_name=self._goto_target_name,
        )
        self._goto_target_name = None

    def _cancel_goto(self, result: str, *, reason: str | None = None) -> None:
        if self._goto_pending:
            self._resolve_goto(result, reason=reason, keep_record=False)
        else:
            self._clear_goto(reason=reason)

    def _clear_goto(self, *, reason: str | None = None) -> None:
        if self._last_goto_time is None:
            return
        logger.debug(
            "dwarf.telescope.goto_cleared",
            reason=reason,
            last_target=self._last_goto_target,
        )
        self._goto_completion_event.set()
        self._goto_pending = False
        self._goto_waiting_for_tracking = False
        self._drop_goto_record()

    def _has_recent_goto(self) -> bool:
        max_age_value = self.settings.goto_valid_seconds
        max_age = float(max_age_value) if max_age_value is not None else 0.0
        if max_age <= 0.0:
            return True
        if self._last_goto_time is None:
            return False
        return (time.time() - self._last_goto_time) <= max_age

    def _has_recent_calibration(self) -> bool:
        max_age_value = self.settings.calibration_valid_seconds
        if self._last_calibration_time is None:
            return False
        if self._last_calibration_ip != self.settings.dwarf_ap_ip:
            return False
        if max_age_value is None:
            return True
        max_age = float(max_age_value)
        if max_age <= 0.0:
            return False
        return (time.time() - self._last_calibration_time) <= max_age

    def _schedule_calibration(self) -> None:
        if self.simulation or not self.settings.auto_calibrate_on_slew:
            return
        if self._has_recent_calibration():
            return
        task = self._calibration_task
        if task and not task.done():
            return
        self._calibration_task = asyncio.create_task(self._run_calibration_task())
        self._calibration_task.add_done_callback(self._on_calibration_task_done)

    async def _run_calibration_task(self) -> None:
        try:
            await self.ensure_calibration()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pragma: no cover - hardware dependent
            logger.warning(
                "dwarf.telescope.calibration.background_failed",
                error=str(exc),
                error_type=type(exc).__name__,
            )

    def _on_calibration_task_done(self, task: asyncio.Task[None]) -> None:
        if task.cancelled():
            logger.debug("dwarf.telescope.calibration.background_cancelled")
        else:
            with contextlib.suppress(Exception):
                task.result()
        if self._calibration_task is task:
            self._calibration_task = None

    async def _wait_for_calibration_ready(self) -> None:
        if self.simulation or not self.settings.auto_calibrate_on_slew:
            return
        self._schedule_calibration()
        task = self._calibration_task
        if not task:
            return
        timeout_value = float(self.settings.calibration_wait_for_slew_seconds)
        if timeout_value <= 0.0:
            return
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=timeout_value)
        except asyncio.TimeoutError:
            logger.info(
                "dwarf.telescope.calibration.wait_timeout",
                timeout=timeout_value,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pragma: no cover - defensive logging helper
            logger.warning(
                "dwarf.telescope.calibration.wait_failed",
                error=str(exc),
                error_type=type(exc).__name__,
            )

    async def _autofocus_before_calibration(self) -> None:
        timeout = max(
            1.0, float(self.settings.calibration_autofocus_timeout_seconds)
        )
        deadline = time.monotonic() + timeout
        self._autofocus_completion_event.clear()
        self._calibration_status = "autofocusing"
        self._calibration_detail = "Astronomical autofocus is starting"
        request = ReqAstroAutoFocus(mode=1)
        logger.info("dwarf.focus.autofocus.before_calibration.starting", timeout=timeout)
        response = await self._send_and_check(
            protocol_pb2.ModuleId.MODULE_FOCUS,
            protocol_pb2.DwarfCMD.CMD_FOCUS_START_ASTRO_AUTO_FOCUS,
            request,
            timeout=timeout,
            expected_responses={
                (
                    protocol_pb2.ModuleId.MODULE_NOTIFY,
                    protocol_pb2.DwarfCMD.CMD_NOTIFY_ASTRO_AUTO_FOCUS_STATE,
                ): AstroAutoFocusState,
                (
                    protocol_pb2.ModuleId.MODULE_NOTIFY,
                    protocol_pb2.DwarfCMD.CMD_NOTIFY_ASTRO_AUTO_FOCUS_FAST_STATE,
                ): AstroAutoFocusFastState,
            },
        )
        # A normal command response is only an acknowledgement. Notification
        # state=3 is the shared V3 evidence that autofocus actually completed.
        # Older test doubles return None and represent a completed call.
        completed_in_response = isinstance(
            response, (AstroAutoFocusState, AstroAutoFocusFastState)
        ) and int(response.state) == 3
        if response is not None and not completed_in_response:
            remaining = max(0.0, deadline - time.monotonic())
            await asyncio.wait_for(
                self._autofocus_completion_event.wait(), timeout=remaining
            )
        self._calibration_status = "autofocus completed"
        self._calibration_detail = "Starting mount calibration"
        logger.info("dwarf.focus.autofocus.before_calibration.completed")

    def _has_recent_calibration_autofocus(self) -> bool:
        if self._calibration_autofocus_time is None:
            return False
        if self._calibration_autofocus_ip != self.settings.dwarf_ap_ip:
            return False
        return (time.time() - self._calibration_autofocus_time) <= 300.0

    async def _prepare_calibration_autofocus(self) -> tuple[float, float]:
        latitude, longitude = self._require_observer_location()
        if not self._has_recent_calibration_autofocus():
            await self._autofocus_before_calibration()
            self._calibration_autofocus_time = time.time()
            self._calibration_autofocus_ip = self.settings.dwarf_ap_ip
        self._calibration_status = "awaiting target"
        self._calibration_detail = "Calibration will run with the next GoTo target"
        return latitude, longitude

    async def prepare_calibration_for_first_slew(self) -> None:
        """Autofocus now; defer target-based V3 calibration to the first slew."""

        if self.simulation or self._has_recent_calibration():
            return
        await self._ensure_ws()
        async with self._calibration_lock:
            if not self._has_recent_calibration():
                await self._prepare_calibration_autofocus()

    async def _prepare_one_click_goto_mode(self) -> None:
        """Mirror the app's V3 mode/camera setup immediately before command 11013."""

        mode_switch = ReqSwitchShootingMode(mode=8)
        response = await self._send_request(
            _MODULE_DEVICE_CONFIG,
            _CMD_TASK_SWITCH_SHOOTING_MODE,
            mode_switch,
            ResSwitchShootingMode,
            timeout=8.0,
        )
        code = int(getattr(response, "code", protocol_pb2.OK))
        mode = int(getattr(response, "shooting_mode_id", 0))
        if code != protocol_pb2.OK or mode != 8:
            raise CaptureConfigurationError(
                f"{self.profile.display_name} did not select astronomy mode "
                f"(code {code}, mode {mode})"
            )

        enter_request = ReqEnterCamera()
        enter_request.client_param.encode_type = 1
        enter_response = await self._send_request(
            _MODULE_DEVICE_CONFIG,
            _CMD_TASK_ENTER_CAMERA,
            enter_request,
            ResEnterCamera,
            timeout=8.0,
        )
        enter_code = int(getattr(enter_response, "code", protocol_pb2.OK))
        if enter_code != protocol_pb2.OK:
            raise CaptureConfigurationError(
                f"{self.profile.display_name} did not enter the astronomy camera "
                f"(code {enter_code})"
            )

        tele_preview = ReqSetPreviewQuality(level=1)
        await self._send_and_check(
            protocol_pb2.ModuleId.MODULE_CAMERA_TELE,
            protocol_pb2.DwarfCMD.CMD_CAMERA_TELE_SET_PREVIEW_QUALITY,
            tele_preview,
            timeout=8.0,
        )
        wide_preview = ReqSetPreviewQuality(level=1)
        await self._send_and_check(
            protocol_pb2.ModuleId.MODULE_CAMERA_WIDE,
            protocol_pb2.DwarfCMD.CMD_CAMERA_WIDE_SET_PREVIEW_QUALITY,
            wide_preview,
            timeout=8.0,
        )
        logger.info("dwarf.telescope.goto.one_click.mode_ready", mode=mode)

    async def ensure_calibration(self) -> None:
        if self.simulation:
            return
        if self._has_recent_calibration():
            return
        async with self._calibration_lock:
            if self._has_recent_calibration():
                return
            try:
                latitude, longitude = self._require_observer_location()
            except Exception as exc:
                self._calibration_status = "location required"
                self._calibration_detail = str(exc)
                logger.warning(
                    "dwarf.telescope.calibration.location_missing",
                    error=str(exc),
                )
                raise
            try:
                await self._autofocus_before_calibration()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._calibration_status = "autofocus failed"
                self._calibration_detail = str(exc) or type(exc).__name__
                logger.warning(
                    "dwarf.focus.autofocus.before_calibration.failed",
                    error=str(exc),
                    error_type=type(exc).__name__,
                )
                raise
            request = astro_pb2.ReqStartCalibration(lon=longitude, lat=latitude)
            self._calibration_status = "starting"
            self._calibration_detail = None
            self._calibration_azimuth = None
            self._calibration_altitude = None
            self._calibration_result_event.clear()
            logger.info(
                "dwarf.telescope.calibration.starting",
                longitude=longitude,
                latitude=latitude,
            )
            self._begin_calibration_trace(latitude=latitude, longitude=longitude)
            timeout = max(1.0, float(self.settings.calibration_timeout_seconds))
            deadline = time.monotonic() + timeout
            try:
                response = await self._send_and_check(
                    protocol_pb2.ModuleId.MODULE_ASTRO,
                    protocol_pb2.DwarfCMD.CMD_ASTRO_START_CALIBRATION,
                    request,
                    timeout=timeout,
                    expected_responses={
                        (
                            protocol_pb2.ModuleId.MODULE_NOTIFY,
                            protocol_pb2.DwarfCMD.CMD_NOTIFY_CALIBRATION_RESULT,
                        ): CalibrationResult,
                    },
                )
                # A ComResponse only acknowledges command 11000. Every V3 model
                # must still wait for the solved-coordinate result on 15256.
                # Older test doubles return None and represent a completed call.
                if response is not None and not isinstance(response, CalibrationResult):
                    remaining = max(0.0, deadline - time.monotonic())
                    await asyncio.wait_for(
                        self._calibration_result_event.wait(), timeout=remaining
                    )
            except asyncio.CancelledError as exc:
                self._finish_calibration_trace(outcome="cancelled", error=exc)
                raise
            except asyncio.TimeoutError as exc:
                self._calibration_status = "not confirmed"
                self._calibration_detail = "No completion notification before timeout"
                logger.warning(
                    "dwarf.telescope.calibration.outcome",
                    outcome="not_confirmed",
                    reason="completion_notification_timeout",
                )
                self._finish_calibration_trace(outcome="not_confirmed", error=exc)
                raise
            except Exception as exc:
                self._calibration_status = "failed"
                self._calibration_detail = str(exc) or type(exc).__name__
                logger.warning(
                    "dwarf.telescope.calibration.outcome",
                    outcome="failed",
                    error=str(exc),
                    error_type=type(exc).__name__,
                )
                self._finish_calibration_trace(outcome="failed", error=exc)
                raise
            self._last_calibration_time = time.time()
            self._last_calibration_ip = self.settings.dwarf_ap_ip
            if self._calibration_status != "successful":
                self._calibration_status = "successful"
                self._calibration_detail = "Calibration command completed"
            logger.info(
                "dwarf.telescope.calibration.completed",
                outcome="successful",
                azimuth=self._calibration_azimuth,
                altitude=self._calibration_altitude,
            )
            self._finish_calibration_trace(outcome="successful")

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
        timeout_value = max(float(self.settings.goto_command_timeout_seconds), 1.0)
        try:
            await self._send_and_check(
                protocol_pb2.ModuleId.MODULE_ASTRO,
                protocol_pb2.DwarfCMD.CMD_ASTRO_START_GOTO_DSO,
                request,
                timeout=timeout_value,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "dwarf.telescope.goto.timeout",
                ra_hours=ra_hours,
                dec_degrees=dec_degrees,
                target_name=target_name,
                timeout=timeout_value,
            )
            raise
        self._record_goto(ra_hours, dec_degrees, kind=_GOTO_KIND_DSO)
        self._one_click_goto_active = False
        self._mark_goto_pending(kind=_GOTO_KIND_DSO, target_name=target_name)

    async def _start_one_click_goto_command(
        self,
        ra_hours: float,
        dec_degrees: float,
        target_name: str,
    ) -> None:
        latitude, longitude = self._require_observer_location()
        request = astro_pb2.ReqOneClickGotoDSO(
            ra=ra_hours,
            dec=dec_degrees,
            target_name=target_name,
            lon=longitude,
            lat=latitude,
            shooting_mode=2,
            goto_only=False,
        )
        self._calibration_status = "starting with target"
        self._calibration_detail = f"Calibrating before GoTo {target_name}"
        self._calibration_azimuth = None
        self._calibration_altitude = None
        self._calibration_result_event.clear()
        self._begin_calibration_trace(latitude=latitude, longitude=longitude)
        self._one_click_goto_active = True
        logger.info(
            "dwarf.telescope.goto.one_click.starting",
            ra_hours=ra_hours,
            dec_degrees=dec_degrees,
            target_name=target_name,
            longitude=longitude,
            latitude=latitude,
            shooting_mode=2,
            goto_only=False,
        )
        try:
            response_future = await self._begin_request(
                protocol_pb2.ModuleId.MODULE_ASTRO,
                protocol_pb2.DwarfCMD.CMD_ASTRO_START_ONE_CLICK_GOTO_DSO,
                request,
                astro_pb2.ResOneClickGoto,
            )
        except Exception as exc:
            self._calibration_status = "failed"
            self._calibration_detail = str(exc) or type(exc).__name__
            self._finish_calibration_trace(outcome="failed", error=exc)
            if not isinstance(exc, DwarfCommandError) or exc.code not in {
                protocol_pb2.CODE_ASTRO_FUNCTION_BUSY,
                protocol_pb2.CODE_ASTRO_GOTO_FAILED,
            }:
                self._one_click_goto_active = False
            raise
        self._record_goto(ra_hours, dec_degrees, kind=_GOTO_KIND_DSO)
        self._mark_goto_pending(kind=_GOTO_KIND_DSO, target_name=target_name)
        self._one_click_goto_active = True
        old_task = self._one_click_response_task
        if old_task and not old_task.done():
            old_task.cancel()
        self._one_click_response_task = asyncio.create_task(
            self._monitor_one_click_goto_response(response_future)
        )

    async def _monitor_one_click_goto_response(
        self, response_future: asyncio.Future[Message]
    ) -> None:
        timeout = max(
            1.0,
            float(self.settings.calibration_timeout_seconds)
            + float(self.settings.goto_completion_timeout_seconds),
        )
        try:
            response = await asyncio.wait_for(response_future, timeout=timeout)
            code = int(getattr(response, "code", protocol_pb2.OK))
            logger.info(
                "dwarf.telescope.goto.one_click.response",
                step=int(getattr(response, "step", 0)),
                code=code,
                all_end=bool(getattr(response, "all_end", False)),
            )
            if code != protocol_pb2.OK and self._one_click_goto_active:
                error = DwarfCommandError(
                    protocol_pb2.ModuleId.MODULE_ASTRO,
                    protocol_pb2.DwarfCMD.CMD_ASTRO_START_ONE_CLICK_GOTO_DSO,
                    code,
                )
                self._calibration_status = "failed"
                self._calibration_detail = str(error)
                self._finish_calibration_trace(outcome="failed", error=error)
                self._resolve_goto(
                    "failed", reason=f"one_click_code_{code}", keep_record=False
                )
        except asyncio.CancelledError:
            raise
        except asyncio.TimeoutError as exc:
            self._ws_client.cancel_pending(
                protocol_pb2.ModuleId.MODULE_ASTRO,
                protocol_pb2.DwarfCMD.CMD_ASTRO_START_ONE_CLICK_GOTO_DSO,
            )
            if self._one_click_goto_active:
                self._calibration_status = "not confirmed"
                self._calibration_detail = "One-click calibration response timed out"
                self._finish_calibration_trace(outcome="not_confirmed", error=exc)
                self._resolve_goto(
                    "timeout", reason="one_click_response_timeout", keep_record=False
                )
        except Exception as exc:  # pragma: no cover - connection dependent
            if self._one_click_goto_active:
                self._calibration_status = "failed"
                self._calibration_detail = str(exc) or type(exc).__name__
                self._finish_calibration_trace(outcome="failed", error=exc)
                self._resolve_goto(
                    "failed", reason="one_click_response_error", keep_record=False
                )
        finally:
            if self._one_click_response_task is asyncio.current_task():
                self._one_click_response_task = None

    async def wait_for_goto_completion(
        self, *, timeout: float | None = None
    ) -> tuple[str, str | None]:
        if self.simulation:
            return "simulation", None
        if not self._goto_pending:
            return self._goto_result or "idle", self._goto_reason

        wait_timeout = (
            timeout if timeout is not None else float(self.settings.goto_completion_timeout_seconds)
        )
        if wait_timeout is not None and self._one_click_goto_active:
            wait_timeout += float(self.settings.calibration_timeout_seconds)
        if wait_timeout is not None and wait_timeout <= 0.0:
            wait_timeout = None

        if wait_timeout is None:
            await self._goto_completion_event.wait()
        else:
            await asyncio.wait_for(self._goto_completion_event.wait(), timeout=wait_timeout)

        return self._goto_result or "unknown", self._goto_reason

    async def telescope_abort_slew(self) -> None:
        one_click = self._one_click_goto_active
        if one_click:
            task = self._one_click_response_task
            if task and not task.done():
                task.cancel()
            self._one_click_response_task = None
            self._ws_client.cancel_pending(
                protocol_pb2.ModuleId.MODULE_ASTRO,
                protocol_pb2.DwarfCMD.CMD_ASTRO_START_ONE_CLICK_GOTO_DSO,
            )
        self._cancel_goto("aborted", reason="slew_aborted")
        if self.simulation:
            return
        await self._ensure_ws()
        request = (
            astro_pb2.ReqStopOneClickGoto() if one_click else ReqStopGoto()
        )
        await self._send_and_check(
            protocol_pb2.ModuleId.MODULE_ASTRO,
            (
                protocol_pb2.DwarfCMD.CMD_ASTRO_STOP_ONE_CLICK_GOTO
                if one_click
                else protocol_pb2.DwarfCMD.CMD_ASTRO_STOP_GOTO
            ),
            request,
        )
        for axis in (0, 1):
            with contextlib.suppress(Exception):
                await self.telescope_stop_axis(axis, ensure_ws=False)

    # --- Camera --------------------------------------------------------------------

    async def camera_connect(self) -> None:
        if self.simulation:
            self.camera_state.connected = True
            return
        await self._ensure_ws()
        if self._uses_v3_protocol():
            request = ReqEnterCamera()
            request.client_param.encode_type = 1
            try:
                response = await self._send_request(
                    _MODULE_DEVICE_CONFIG,
                    _CMD_TASK_ENTER_CAMERA,
                    request,
                    ResEnterCamera,
                    timeout=2.0,
                    suppress_timeout_warning=True,
                    close_ws_on_timeout=False,
                )
            except asyncio.TimeoutError:
                # Current Mini firmware acknowledges the global task-manager
                # entry command, while the tested DWARF 3 firmware silently
                # ignores it and still accepts the camera command below. The
                # latter has the same wire payload as the formerly documented
                # V3 OpenTeleCamera action=1 command.
                logger.warning(
                    "dwarf.camera.enter_camera_unacknowledged",
                    model=self.profile.model_id,
                    command_id=_CMD_TASK_ENTER_CAMERA,
                    fallback_command=protocol_pb2.DwarfCMD.CMD_CAMERA_TELE_SET_PREVIEW_QUALITY,
                )
            else:
                if int(response.code) != protocol_pb2.OK:
                    raise DwarfCommandError(
                        _MODULE_DEVICE_CONFIG,
                        _CMD_TASK_ENTER_CAMERA,
                        int(response.code),
                    )
            await self._send_and_check(
                protocol_pb2.ModuleId.MODULE_CAMERA_TELE,
                protocol_pb2.DwarfCMD.CMD_CAMERA_TELE_SET_PREVIEW_QUALITY,
                ReqSetPreviewQuality(level=1),
            )
            self.camera_state.connected = True
            return

        request = ReqOpenCamera()
        request.binning = False
        request.rtsp_encode_type = 0
        await self._send_and_check(
            protocol_pb2.ModuleId.MODULE_CAMERA_TELE,
            protocol_pb2.DwarfCMD.CMD_CAMERA_TELE_OPEN_CAMERA,
            request,
        )
        self.camera_state.connected = True

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
        if self._uses_v3_protocol():
            # The V3 app captures do not send the legacy camera command 10001;
            # it leaves shared mode/stream ownership to the global task manager.
            # A Camera-only Alpaca disconnect must not disturb a connected mount.
            logger.info("dwarf.camera.disconnect.local_only", protocol_family="v3")
            return

        await self._ensure_ws()
        request = ReqCloseCamera()
        timeout_value = max(float(self.settings.camera_disconnect_timeout_seconds), 0.5)
        try:
            await self._send_and_check(
                protocol_pb2.ModuleId.MODULE_CAMERA_TELE,
                protocol_pb2.DwarfCMD.CMD_CAMERA_TELE_CLOSE_CAMERA,
                request,
                timeout=timeout_value,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "dwarf.camera.disconnect.timeout",
                timeout=timeout_value,
            )
        except DwarfCommandError as exc:
            logger.warning(
                "dwarf.camera.disconnect.command_failed",
                code=exc.code,
                module_id=exc.module_id,
                command_id=exc.command_id,
            )
        except (ConnectionClosed, ConnectionClosedOK) as exc:
            logger.info(
                "dwarf.camera.disconnect.socket_closed",
                error=str(exc),
                error_type=type(exc).__name__,
            )
        except Exception as exc:  # pragma: no cover - defensive logging helper
            logger.warning(
                "dwarf.camera.disconnect.error",
                error=str(exc),
                error_type=type(exc).__name__,
            )

    async def camera_start_exposure(
        self,
        duration: float,
        light: bool,
        *,
        continue_without_darks: bool | None = None,
    ) -> None:
        state = self.camera_state
        if state.capture_task and not state.capture_task.done():
            raise CaptureBusyError("capture_already_in_progress")
        if state.capture_phase in {
            CapturePhase.CONFIGURING,
            CapturePhase.WAITING_FOR_DARK,
            CapturePhase.STARTING,
            CapturePhase.EXPOSING,
            CapturePhase.PROCESSING,
            CapturePhase.TRANSFERRING,
            CapturePhase.ABORTING,
        }:
            raise CaptureBusyError("capture_already_in_progress")
        mini_profile = self._is_dwarf_mini()
        if mini_profile and not light:
            state.capture_phase = CapturePhase.FAILED
            state.last_error = "mini_dark_calibration_unverified"
            raise CaptureConfigurationError(
                "DWARF mini dark frames use the dedicated calibration workflow; "
                "image delivery to NINA has not yet been hardware-verified"
            )
        if not self.simulation:
            await self._ensure_ws()
            await self._wait_for_astro_capture_ready()
        state.capture_id = uuid.uuid4().hex
        capture_id = state.capture_id
        state.capture_phase = CapturePhase.CONFIGURING
        state.capture_start_monotonic = time.monotonic()
        state.duration = duration
        state.light = light
        state.start_time = time.time()
        state.last_start_time = state.start_time
        state.last_end_time = None
        state.image_timestamp = None
        state.last_error = None
        state.image = None
        state.source_format = None
        state.source_bit_depth = None
        state.applied_duration = None
        state.reported_duration = None
        state.applied_gain_value = None
        state.applied_filter_name = None
        state.applied_bin = None
        state.applied_frame_count = None
        state.progress_total_count = None
        state.progress_current_count = 0
        state.progress_stacked_count = 0
        state.progress_exposure_index = None
        state.progress_gain_index = None
        state.progress_target_name = None
        state.retrieved_file_path = None
        self._capture_frame_complete_event.clear()
        self._v3_selected_astro_preset = None
        self._v3_runtime_reapply_capture_id = None
        self._v3_capture_param_mode_id = None
        state.last_dark_check_code = None
        state.capture_mode = self._resolve_mini_capture_mode() if mini_profile else "astro"
        frames_to_capture = max(1, int(state.requested_frame_count or 1))
        state.requested_frame_count = frames_to_capture
        if self.simulation:
            await self._simulate_capture(state)
            state.capture_task = None
            state.applied_duration = duration
            state.applied_gain_value = state.requested_gain
            state.applied_filter_name = state.filter_name or None
            state.applied_bin = state.requested_bin
            state.applied_frame_count = frames_to_capture
            state.capture_phase = CapturePhase.READY
            return

        if continue_without_darks is None:
            continue_without_darks = self.settings.allow_continue_without_darks

        if state.capture_mode == "photo" and not self.settings.allow_unverified_direct_photo:
            raise CaptureConfigurationError(
                "Direct photo capture is experimental because exposure, gain, and raw output "
                "cannot be independently confirmed; use the astro workflow"
            )

        await self._enter_v3_astro_mode()
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

        if mini_profile and state.capture_mode == "photo":
            if frames_to_capture != 1 or (bin_x, bin_y) != (1, 1):
                raise CaptureConfigurationError(
                    "Direct photo capture cannot guarantee frame count or binning"
                )
            await self._refresh_capture_baseline(capture_kind=state.capture_mode)
            try:
                photo_timeout = max(duration + 2.0, 5.0)
                started = await self._start_photo_capture(timeout=photo_timeout)
            except DwarfCommandError as exc:
                state.last_error = f"command_error:{exc.code}"
                raise
            except asyncio.TimeoutError:
                state.last_error = "timeout"
                raise
            except Exception:
                state.last_error = "command_error:photo_start_failed"
                raise
            if not started:
                state.last_error = "command_error:photo_start_failed"
                raise RuntimeError("photo_start_failed")
            state.last_error = None
            state.capture_phase = CapturePhase.EXPOSING
            logger.info(
                "dwarf.camera.photo_capture_started",
                duration=duration,
                light=light,
                frames=frames_to_capture,
                binning=(bin_x, bin_y),
            )
            state.capture_task = asyncio.create_task(self._fetch_capture(state))
            return

        if light and self.settings.go_live_before_exposure:
            await self._astro_go_live()

        dark_ready = True
        if light:
            state.capture_phase = CapturePhase.WAITING_FOR_DARK
            try:
                dark_ready = await self._ensure_dark_library(
                    continue_without_darks=continue_without_darks
                )
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
        state.capture_phase = CapturePhase.STARTING
        await self._refresh_capture_baseline(capture_kind=state.capture_mode)

        if state.capture_id != capture_id or state.capture_phase != CapturePhase.STARTING:
            logger.info(
                "dwarf.camera.astro_capture_start_cancelled",
                capture_id=capture_id,
                active_capture_id=state.capture_id,
                capture_phase=state.capture_phase.value,
            )
            return

        astro_code = protocol_pb2.OK
        try:
            astro_code = await self._start_astro_capture(
                timeout=command_timeout,
                force_on_dark_warning=bool(continue_without_darks),
            )
            if self._uses_v3_protocol() and self._v3_live_parameters_supported:
                try:
                    requested_gain = state.requested_gain
                    if requested_gain is None:
                        requested_gain = int(self.profile.camera.min_gain_db)
                    await self._apply_v3_capture_runtime_parameters(
                        duration,
                        int(requested_gain),
                        frames_to_capture,
                    )
                except Exception as exc:
                    # 11005 is already running at this point. Never turn a
                    # best-effort runtime correction into a failed Alpaca
                    # StartExposure while the device continues capturing.
                    logger.warning(
                        "dwarf.camera.v3_capture_runtime_params_failed",
                        error=str(exc),
                        error_type=type(exc).__name__,
                    )
        except DwarfCommandError as exc:
            if exc.code == protocol_pb2.CODE_ASTRO_FUNCTION_BUSY:
                state.last_error = "astro_busy"
            else:
                state.last_error = f"command_error:{exc.code}"
            state.capture_id = None
            state.capture_phase = CapturePhase.FAILED
            state.start_time = None
            raise
        except asyncio.TimeoutError:
            state.last_error = "timeout"
            state.capture_id = None
            state.capture_phase = CapturePhase.FAILED
            state.start_time = None
            raise
        except Exception:
            state.capture_id = None
            state.capture_phase = CapturePhase.FAILED
            state.start_time = None
            raise

        if state.capture_id != capture_id or state.capture_phase != CapturePhase.STARTING:
            logger.info(
                "dwarf.camera.astro_capture_started_then_aborted",
                capture_id=capture_id,
                active_capture_id=state.capture_id,
                capture_phase=state.capture_phase.value,
            )
            return

        if astro_code == protocol_pb2.CODE_ASTRO_NEED_GOTO:
            logger.warning(
                "dwarf.camera.astro_capture_goto_warning_ignored",
                duration=duration,
                light=light,
                goto_target=self._last_goto_target,
                code=astro_code,
            )

        state.last_error = None
        state.capture_phase = CapturePhase.EXPOSING
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
        if not self.simulation and state.capture_mode != "astro":
            raise CaptureConfigurationError("abort_not_supported_for_photo_workflow")
        state.capture_id = None
        state.capture_phase = CapturePhase.ABORTING
        if state.capture_task and not state.capture_task.done():
            state.capture_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await state.capture_task
        if not self.simulation:
            await self._stop_astro_capture(strict=True)
        state.capture_task = None
        state.start_time = None
        state.image = None
        state.last_end_time = time.time()
        state.image_timestamp = None
        state.last_error = "aborted"
        state.capture_phase = CapturePhase.IDLE

    async def camera_readout(self) -> Optional[np.ndarray]:
        state = self.camera_state
        if state.capture_phase != CapturePhase.READY:
            return None
        return state.image

    async def _get_v3_astro_presets(self) -> list[V3AstroPreset]:
        if self._v3_astro_presets is not None:
            return self._v3_astro_presets
        request = astro_pb2.ReqGetQuickSetList(camera_type=0)
        response = await self._send_request(
            protocol_pb2.ModuleId.MODULE_ASTRO,
            protocol_pb2.DwarfCMD.CMD_ASTRO_GET_QUICK_SET_LIST,
            request,
            astro_pb2.ResGetQuickSetList,
            timeout=8.0,
        )
        code = int(getattr(response, "code", protocol_pb2.OK))
        if code != protocol_pb2.OK:
            raise CaptureConfigurationError(
                f"{self.profile.display_name} V3 astro-parameter discovery failed with code {code}"
            )

        presets: list[V3AstroPreset] = []
        for entry in response.quick_set_list:
            parts = tuple(str(entry.info_id).split("|"))
            if len(parts) < 6:
                continue
            try:
                exposure_s = float(parts[2])
                gain = int(parts[3])
                # The fifth quick-set component is resolution (DWARF 3 uses 0
                # for its native raw array; Mini uses 1 for native 1080p).
                # Frame count is a separate 16703 parameter and must never be
                # written into this tuple position.
                resolution_index = int(parts[4])
            except (TypeError, ValueError):
                continue
            if exposure_s <= 0:
                continue
            presets.append(
                V3AstroPreset(
                    exposure_s=exposure_s,
                    gain=gain,
                    resolution_index=resolution_index,
                    pipe_parts=parts,
                )
            )
        if not presets:
            raise CaptureConfigurationError(
                f"{self.profile.display_name} returned no usable V3 astronomy exposure presets"
            )
        self._v3_astro_presets = presets
        logger.info(
            "dwarf.camera.v3_astro_presets_loaded",
            presets=[{"exposure": preset.exposure_s, "gain": preset.gain} for preset in presets],
        )
        return presets

    async def _select_v3_astro_preset(self, duration: float) -> V3AstroPreset:
        presets = await self._get_v3_astro_presets()
        camera = self.profile.camera
        if duration < camera.min_exposure_s or duration > camera.max_exposure_s:
            raise CaptureConfigurationError(
                f"Requested exposure {duration:g}s is outside the {self.profile.display_name} range "
                f"{camera.min_exposure_s:g}s to {camera.max_exposure_s:g}s"
            )
        requested_gain = self.camera_state.requested_gain
        if requested_gain is None:
            requested_gain = int(camera.min_gain_db)
        requested_gain = int(requested_gain)
        if requested_gain < camera.min_gain_db or requested_gain > camera.max_gain_db:
            raise CaptureConfigurationError(
                f"Requested gain {requested_gain} is outside the {self.profile.display_name} range "
                f"{camera.min_gain_db:g} to {camera.max_gain_db:g}"
            )
        template = min(
            presets,
            key=lambda preset: (
                abs(preset.exposure_s - duration),
                abs(preset.gain - requested_gain),
            ),
        )
        parts = list(template.pipe_parts)
        parts[2] = f"{duration:g}"
        parts[3] = str(requested_gain)
        selected = V3AstroPreset(
            exposure_s=duration,
            gain=requested_gain,
            resolution_index=template.resolution_index,
            pipe_parts=tuple(parts),
        )
        self._v3_selected_astro_preset = selected
        self.camera_state.applied_duration = duration
        return selected

    async def _get_v3_astro_param_catalog(self) -> dict[str, Any]:
        if self._v3_astro_param_catalog is not None:
            return self._v3_astro_param_catalog
        response = await self._http_client.get_param_and_setting(_V3_ASTRO_MODE_ID)
        if not isinstance(response, dict) or int(response.get("code", -1)) != 0:
            raise CaptureConfigurationError(
                f"{self.profile.display_name} parameter catalogue request failed"
            )
        data = response.get("data")
        if not isinstance(data, dict):
            raise CaptureConfigurationError(
                f"{self.profile.display_name} returned no astronomy parameter catalogue"
            )
        self._v3_astro_param_catalog = data
        return data

    async def _resolve_v3_astro_controls(
        self, duration: float, gain: int
    ) -> tuple[int, int, int, int]:
        catalog = await self._get_v3_astro_param_catalog()
        camera_params = catalog.get("cameraParams")
        if not isinstance(camera_params, list):
            raise CaptureConfigurationError("V3 astronomy camera parameters are unavailable")
        tele = next(
            (
                item
                for item in camera_params
                if isinstance(item, dict) and int(item.get("cameraId", -1)) == 0
            ),
            None,
        )
        special = tele.get("specialParams") if isinstance(tele, dict) else None
        exposure_param = special.get("exp") if isinstance(special, dict) else None
        gain_param = special.get("gain") if isinstance(special, dict) else None
        if not isinstance(exposure_param, dict) or not isinstance(gain_param, dict):
            raise CaptureConfigurationError("V3 astronomy exposure/gain controls are unavailable")

        values = exposure_param.get("values")
        choices: list[tuple[float, int, str]] = []
        if isinstance(values, list):
            for item in values:
                if not isinstance(item, dict):
                    continue
                label = str(item.get("name", "")).strip()
                try:
                    seconds = exposure.parse_exposure_seconds(label)
                    index = int(item["value"])
                except (KeyError, TypeError, ValueError):
                    continue
                if seconds is not None and seconds > 0:
                    choices.append((seconds, index, label))
        match = next(
            (choice for choice in choices if math.isclose(choice[0], duration, rel_tol=1e-6, abs_tol=1e-6)),
            None,
        )
        if match is None:
            supported = ", ".join(choice[2] for choice in choices if choice[0] >= 1.0)
            raise CaptureConfigurationError(
                f"No exact firmware exposure value is available for requested duration {duration:g}s"
                + (f" (supported: {supported})" if supported else "")
            )

        gain_values = gain_param.get("values")
        if isinstance(gain_values, list) and gain not in {
            int(value) for value in gain_values if isinstance(value, (int, float))
        }:
            raise CaptureConfigurationError(
                f"Gain {gain} is not supported by the active V3 astronomy mode"
            )
        return (
            int(exposure_param.get("paramId", _V3_ASTRO_EXPOSURE_PARAM_ID)),
            match[1],
            int(gain_param.get("paramId", _V3_ASTRO_GAIN_PARAM_ID)),
            gain,
        )

    async def _apply_v3_astro_exposure_gain(self, duration: float, gain: int) -> None:
        exposure_param_id, exposure_index, gain_param_id, gain_value = (
            await self._resolve_v3_astro_controls(duration, gain)
        )
        expected = {
            (_MODULE_CAMERA_PARAMS, _CMD_NOTIFY_GENERAL_INT_PARAM): GeneralIntParam,
            (
                protocol_pb2.ModuleId.MODULE_NOTIFY,
                _CMD_NOTIFY_GENERAL_INT_PARAM,
            ): GeneralIntParam,
        }
        exp_request = ReqSetExposure()
        exp_request.param_id = exposure_param_id
        exp_request.mode = 1  # manual
        exp_request.value = exposure_index
        await self._send_and_check(
            _MODULE_CAMERA_PARAMS,
            _CMD_PARAM_SET_EXPOSURE,
            exp_request,
            expected_responses=expected,
        )
        gain_request = ReqSetExposure()
        gain_request.param_id = gain_param_id
        gain_request.mode = 1  # manual
        gain_request.value = gain_value
        await self._send_and_check(
            _MODULE_CAMERA_PARAMS,
            _CMD_PARAM_SET_GAIN,
            gain_request,
            expected_responses=expected,
        )
        self.camera_state.exposure_index = exposure_index
        self.camera_state.applied_duration = duration
        self.camera_state.applied_gain_value = gain_value
        logger.info(
            "dwarf.camera.v3_astro_exposure_gain_applied",
            exposure=duration,
            exposure_index=exposure_index,
            exposure_param_id=exposure_param_id,
            gain=gain_value,
            gain_param_id=gain_param_id,
        )

    @staticmethod
    def _v3_param_id_for_mode(param_id: int, mode_id: int) -> int:
        return (int(mode_id) << _V3_PARAM_MODE_SHIFT) | (
            int(param_id) & _V3_PARAM_MODE_VALUE_MASK
        )

    async def _apply_v3_capture_runtime_parameters(
        self,
        duration: float,
        gain: int,
        frames: int,
        *,
        mode_id: int | None = None,
    ) -> None:
        """Override the firmware-selected capture namespace after 11005 starts."""

        exposure_param_id, exposure_index, gain_param_id, gain_value = (
            await self._resolve_v3_astro_controls(duration, gain)
        )
        capture_mode_id = (
            int(mode_id) if mode_id is not None else _V3_ASTRO_CAPTURE_MODE_ID
        )
        capture_exposure_param_id = self._v3_param_id_for_mode(
            exposure_param_id, capture_mode_id
        )
        capture_gain_param_id = self._v3_param_id_for_mode(
            gain_param_id, capture_mode_id
        )
        expected = {
            (_MODULE_CAMERA_PARAMS, _CMD_NOTIFY_GENERAL_INT_PARAM): GeneralIntParam,
            (
                protocol_pb2.ModuleId.MODULE_NOTIFY,
                _CMD_NOTIFY_GENERAL_INT_PARAM,
            ): GeneralIntParam
        }
        exp_request = ReqSetExposure(
            param_id=capture_exposure_param_id,
            mode=1,
            value=exposure_index,
        )
        await self._send_and_check(
            _MODULE_CAMERA_PARAMS,
            _CMD_PARAM_SET_EXPOSURE,
            exp_request,
            expected_responses=expected,
        )
        gain_request = ReqSetExposure(
            param_id=capture_gain_param_id,
            mode=1,
            value=gain_value,
        )
        await self._send_and_check(
            _MODULE_CAMERA_PARAMS,
            _CMD_PARAM_SET_GAIN,
            gain_request,
            expected_responses=expected,
        )
        capture_frame_param_id = self._v3_param_id_for_mode(
            _V3_ASTRO_FRAME_COUNT_PARAM_ID, capture_mode_id
        )
        frame_request = ReqSetGeneralIntParam(
            param_id=capture_frame_param_id,
            value=max(1, int(frames)),
        )
        await self._send_and_check(
            _MODULE_CAMERA_PARAMS,
            _CMD_PARAM_SET_GENERAL_INT,
            frame_request,
            timeout=3.0,
            expected_responses=expected,
            close_ws_on_timeout=False,
        )
        logger.info(
            "dwarf.camera.v3_capture_runtime_params_applied",
            mode_id=capture_mode_id,
            exposure=duration,
            exposure_index=exposure_index,
            exposure_param_id=capture_exposure_param_id,
            gain=gain_value,
            gain_param_id=capture_gain_param_id,
            frames=frame_request.value,
            frame_param_id=capture_frame_param_id,
        )

    async def _apply_v3_astro_quick_set(
        self,
        duration: float,
        gain: int,
        frames: int,
    ) -> None:
        """Prime the persisted sequence that command 11005 loads."""

        selected = await self._select_v3_astro_preset(duration)
        parts = list(selected.pipe_parts)
        parts[3] = str(int(gain))
        request = astro_pb2.ReqSetQuickSet(info_id="|".join(parts))
        response = await self._send_request(
            protocol_pb2.ModuleId.MODULE_ASTRO,
            protocol_pb2.DwarfCMD.CMD_ASTRO_SET_QUICK_SET,
            request,
            astro_pb2.ResSetQuickSet,
            timeout=8.0,
        )
        code = int(getattr(response, "code", protocol_pb2.OK))
        if code != protocol_pb2.OK:
            raise CaptureConfigurationError(
                f"{self.profile.display_name} rejected astronomy quick-set parameters "
                f"with code {code}"
            )
        logger.info(
            "dwarf.camera.v3_astro_quick_set_applied",
            info_id=request.info_id,
            response_info_id=str(getattr(response, "info_id", "")),
            exposure=duration,
            gain=gain,
            frames=frames,
            resolution_index=selected.resolution_index,
        )

    async def _ensure_exposure_settings(self, duration: float) -> None:
        if self.simulation:
            return
        state = self.camera_state
        if self._uses_v3_protocol():
            requested_gain = state.requested_gain
            if requested_gain is None:
                requested_gain = int(self.profile.camera.min_gain_db)
            await self._resolve_v3_astro_controls(duration, int(requested_gain))
            state.applied_duration = duration
            return
        resolver = await self._get_exposure_resolver()
        option = resolver.choose_option(duration) if resolver else None
        if option is None:
            logger.error("dwarf.camera.exposure_index_missing", requested_duration=duration)
            raise CaptureConfigurationError(
                f"No firmware exposure value is available for requested duration {duration:g}s"
            )
        index = option.index
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
            raise CaptureConfigurationError(
                f"DWARF rejected exposure {duration:g}s (firmware index {index})"
            ) from exc
        except Exception as exc:  # pragma: no cover - hardware dependent
            if isinstance(exc, CaptureConfigurationError):
                raise
            logger.warning(
                "dwarf.camera.exposure_config_failed",
                error=str(exc),
                error_type=type(exc).__name__,
                requested_duration=duration,
                index=index,
            )
            raise CaptureConfigurationError(
                f"Could not apply exposure {duration:g}s (firmware index {index})"
            ) from exc
        else:
            state.exposure_index = index
            state.applied_duration = option.seconds
            if not math.isclose(option.seconds, duration, rel_tol=0.0, abs_tol=1e-9):
                logger.info(
                    "dwarf.camera.exposure_snapped",
                    requested_duration=duration,
                    applied_duration=option.seconds,
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
        self._filter_options = None
        self._gain_support_param = None
        self._gain_value_options = None
        self._gain_manual_mode_supported = None
        self._gain_last_skipped_value = None
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
            params = []
        else:
            data = self._params_config.get("data")
            if not isinstance(data, dict):
                params = []
            else:
                params = data.get("featureParams")
                if not isinstance(params, list):
                    params = []
        for entry in params:
            if isinstance(entry, dict):
                yield entry
        ws_params = self._ws_feature_params or []
        for entry in ws_params:
            if isinstance(entry, dict):
                yield entry

    @staticmethod
    def _common_param_to_dict(param: Message) -> dict[str, Any]:
        return {
            "id": int(getattr(param, "id", 0)),
            "hasAuto": bool(getattr(param, "hasAuto", False)),
            "autoMode": int(getattr(param, "auto_mode", 0)),
            "modeIndex": int(getattr(param, "mode_index", 0)),
            "index": int(getattr(param, "index", 0)),
            "continueValue": float(getattr(param, "continue_value", 0.0)),
            "name": "",
        }

    async def _ensure_ws_feature_params(self) -> None:
        if self.simulation or not self._is_dwarf_mini():
            return
        if self._ws_feature_params is not None:
            return
        try:
            await self._ensure_ws()
            request = ReqGetAllFeatureParams()
            response = await self._send_request(
                protocol_pb2.ModuleId.MODULE_CAMERA_TELE,
                protocol_pb2.DwarfCMD.CMD_CAMERA_TELE_GET_ALL_FEATURE_PARAMS,
                request,
                ResGetAllFeatureParams,
                timeout=8.0,
                suppress_timeout_warning=True,
                close_ws_on_timeout=False,
            )
        except Exception as exc:  # pragma: no cover - hardware dependent
            if isinstance(exc, asyncio.TimeoutError):
                logger.debug("dwarf.camera.ws_feature_params_fetch_timeout")
            else:
                logger.warning("dwarf.camera.ws_feature_params_fetch_failed", error=str(exc))
            self._ws_feature_params = []
            return

        self._ws_feature_params = [
            self._common_param_to_dict(param) for param in response.all_feature_params
        ]
        for entry in self._ws_feature_params:
            param_id = entry.get("id")
            if not self._is_likely_filter_param_id(param_id):
                continue
            try:
                self._ws_v3_filter_param_id = int(param_id)
                self._ws_v3_filter_param_flag = int(entry.get("modeIndex", 0))
                self._ws_v3_filter_value = int(entry.get("index", 0))
            except (TypeError, ValueError):
                continue
            break
        logger.info(
            "dwarf.camera.ws_feature_params_loaded",
            count=len(self._ws_feature_params),
            filter_param_id=self._ws_v3_filter_param_id,
            filter_value=self._ws_v3_filter_value,
        )

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
    def _extract_feature_options(
        feature: dict[str, Any],
    ) -> list[tuple[int | None, int, str, float | None]]:
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
        fallback_labels = self._fallback_filter_labels()
        if self.profile.filters.control_path == "astro-start-ir-index":
            # V3 applies the physical filter as part of the astronomy-start request,
            # rather than through a standalone filter-wheel movement command.
            self._filter_options = [
                FilterOption(
                    parameter={"__control": "astro_capture_ir_index"},
                    mode_index=0,
                    index=firmware_index,
                    label=label,
                    controllable=True,
                )
                for firmware_index, label in zip(
                    self.profile.filters.firmware_indices,
                    fallback_labels,
                    strict=True,
                )
            ]
            return self._filter_options
        if self.profile.filters.control_path == "v3-camera-param":
            param_id = int(self._ws_v3_filter_param_id or _MINI_DEFAULT_FILTER_PARAM_ID)
            self._filter_options = [
                FilterOption(
                    parameter={
                        "id": param_id,
                        "name": "v3_filter_param",
                        "__control": "v3_camera_param",
                        "__v3_param_id": param_id,
                        "flag": 0,
                    },
                    mode_index=0,
                    index=firmware_index,
                    label=label,
                    controllable=True,
                )
                for firmware_index, label in zip(
                    self.profile.filters.firmware_indices,
                    fallback_labels,
                    strict=True,
                )
            ]
            return self._filter_options
        if self.simulation:
            self._filter_options = [
                FilterOption(
                    parameter={},
                    mode_index=0,
                    index=i,
                    label=_canonical_filter_label(label, i),
                )
                for i, label in enumerate(fallback_labels)
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
                for i, label in enumerate(fallback_labels)
            ]
            logger.info(
                "dwarf.camera.filter_options_fallback",
                filters=fallback_labels,
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
            resolved = self._normalize_filter_label(label, index)
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
            for mode_index, index, label, continue_value in self._extract_support_param_options(
                param
            ):
                _add_option(param, mode_index, index, label, continue_value)

        if not options:
            for feature in self._iter_feature_params():
                feature_name = str(feature.get("name", "")).strip().lower()
                if "filter" not in feature_name:
                    continue
                for mode_index, index, label, continue_value in self._extract_feature_options(
                    feature
                ):
                    _add_option(feature, mode_index, index, label, continue_value)

        if not options and self._is_dwarf_mini():
            # Mini firmware can expose filter-like options under non-filter parameter names.
            for _, param in self._iter_camera_support_params(camera_name="tele"):
                extracted = self._extract_support_param_options(param)
                labels = [label for _, _, label, _ in extracted]
                if not self._looks_like_filter_option_set(labels):
                    continue
                for mode_index, index, label, continue_value in extracted:
                    _add_option(param, mode_index, index, label, continue_value)
            if not options:
                for feature in self._iter_feature_params():
                    extracted = self._extract_feature_options(feature)
                    labels = [label for _, _, label, _ in extracted]
                    if not self._looks_like_filter_option_set(labels):
                        continue
                    for mode_index, index, label, continue_value in extracted:
                        _add_option(feature, mode_index, index, label, continue_value)

        if not options:
            fallback = self._find_feature_option_by_label("filter")
            if fallback is not None:
                feature, option = fallback
                mode_index, index, label, continue_value = option
                _add_option(feature, mode_index, index, label, continue_value)

        if not options and self._is_dwarf_mini():
            await self._ensure_ws_feature_params()

        if not options and self._is_dwarf_mini():
            param_id = int(self._ws_v3_filter_param_id or _MINI_DEFAULT_FILTER_PARAM_ID)
            flag_value = int(self._ws_v3_filter_param_flag)
            options = [
                FilterOption(
                    parameter={
                        "id": param_id,
                        "name": "v3_filter_param",
                        "__control": "v3_camera_param",
                        "__v3_param_id": param_id,
                        "flag": flag_value,
                    },
                    mode_index=flag_value,
                    index=i,
                    label=self._normalize_filter_label(label, i),
                    continue_value=None,
                    controllable=True,
                )
                for i, label in enumerate(fallback_labels)
            ]
            logger.info(
                "dwarf.camera.filter_options_from_ws",
                filter_param_id=param_id,
                filters=[option.label for option in options],
            )

        if not options:
            self._filter_options = [
                FilterOption(
                    parameter=None,
                    mode_index=0,
                    index=i,
                    label=_canonical_filter_label(label, i),
                    controllable=False,
                )
                for i, label in enumerate(fallback_labels)
            ]
            logger.info(
                "dwarf.camera.filter_options_fallback",
                filters=fallback_labels,
                reason="params_config_missing_filters",
            )
        else:
            self._filter_options = self._canonicalize_mini_filter_options(options)
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
            raise CaptureConfigurationError(
                f"Filter {option.label!r} is visible but has no confirmed device control"
            )

        control_mode = str(option.parameter.get("__control", "")).strip().lower()
        if control_mode == "astro_capture_ir_index":
            # The Mini applies this value as part of the next astronomy start
            # request. Remembering it here gives Alpaca clients deterministic
            # FilterWheel semantics without claiming an unsupported standalone
            # motor command.
            state.filter_name = option.label
            state.filter_index = position
            logger.info(
                "dwarf.camera.filter_selected_for_next_capture",
                filter=state.filter_name,
                position=position,
                ir_index=option.index,
            )
            return
        if control_mode == "v3_camera_param":
            raw_param_id = option.parameter.get("__v3_param_id")
            try:
                param_id = int(raw_param_id)
            except (TypeError, ValueError):
                param_id = None
            if param_id is None:
                raise ValueError("invalid_v3_filter_param_id")
            flag_value = option.parameter.get("flag", option.mode_index)
            try:
                flag = int(flag_value)
            except (TypeError, ValueError):
                flag = 0
            await self._set_v3_camera_param(param_id=param_id, value=option.index, flag=flag)
            state.filter_name = option.label
            state.filter_index = position
            state.applied_filter_name = option.label
            self._ws_v3_filter_param_id = param_id
            self._ws_v3_filter_param_flag = flag
            self._ws_v3_filter_value = option.index
            logger.info(
                "dwarf.camera.filter_selected",
                filter=state.filter_name,
                position=position,
                mode_index=option.mode_index,
                index=option.index,
                continue_value=option.continue_value,
                control="v3_camera_param",
            )
            return

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
                strict=True,
            )
        state.filter_name = option.label
        state.filter_index = position
        state.applied_filter_name = option.label
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

    async def _set_v3_camera_param(self, *, param_id: int, value: int, flag: int = 0) -> None:
        if self.simulation:
            return
        expected = {
            (_MODULE_CAMERA_PARAMS, _CMD_NOTIFY_GENERAL_INT_PARAM): GeneralIntParam,
            (
                protocol_pb2.ModuleId.MODULE_NOTIFY,
                _CMD_NOTIFY_GENERAL_INT_PARAM,
            ): GeneralIntParam,
            (
                protocol_pb2.ModuleId.MODULE_NOTIFY,
                protocol_pb2.DwarfCMD.CMD_NOTIFY_SET_FEATURE_PARAM,
            ): ResNotifyParam,
        }

        is_v3_filter_write = self._is_likely_filter_param_id(param_id)
        if is_v3_filter_write:
            candidate_ids: list[int] = []
            preferred_id = self._ws_v3_filter_param_id
            for candidate in (
                int(preferred_id) if preferred_id is not None else None,
                int(param_id),
                _MINI_DEFAULT_FILTER_PARAM_ID,
                _MINI_ALT_FILTER_PARAM_ID,
                13,
            ):
                if candidate is None:
                    continue
                if candidate not in candidate_ids:
                    candidate_ids.append(candidate)

            # Once we have a likely-working param ID, avoid expensive fan-out retries.
            if preferred_id is not None and self._is_likely_filter_param_id(preferred_id):
                candidate_ids = [int(preferred_id)]

            await self._ensure_ws()
            last_error: Exception | None = None
            selected_candidate = int(candidate_ids[0]) if candidate_ids else int(param_id)
            filter_timeout_s = 1.0
            for candidate in candidate_ids:
                adjust_request = ReqSetGeneralIntParam()
                adjust_request.param_id = int(candidate)
                adjust_request.value = int(value)
                try:
                    await self._send_and_check(
                        _MODULE_CAMERA_PARAMS,
                        _CMD_PARAM_SET_GENERAL_INT,
                        adjust_request,
                        timeout=filter_timeout_s,
                        expected_responses=expected,
                        suppress_timeout_warning=True,
                        close_ws_on_timeout=False,
                    )
                    self._ws_v3_filter_param_id = int(candidate)
                    return
                except (DwarfCommandError, asyncio.TimeoutError) as exc:
                    last_error = exc
                    selected_candidate = int(candidate)
                    logger.debug(
                        "dwarf.camera.v3_adjust_param_retry",
                        param_id=int(candidate),
                        value=int(value),
                        error=str(exc),
                        error_type=type(exc).__name__,
                    )

            if last_error is not None:
                self._ws_v3_filter_param_id = int(selected_candidate)
                logger.warning(
                    "dwarf.camera.v3_filter_write_unconfirmed",
                    param_id=int(selected_candidate),
                    value=int(value),
                    flag=int(flag),
                    error=str(last_error),
                    error_type=type(last_error).__name__,
                )
                raise CaptureConfigurationError(
                    f"Filter write was not confirmed for parameter {selected_candidate}"
                ) from last_error

        request = ReqSetExposure()
        request.param_id = int(param_id)
        request.mode = int(flag)
        request.value = int(value)
        try:
            await self._send_and_check(
                _MODULE_CAMERA_PARAMS,
                _CMD_PARAM_SET_EXPOSURE,
                request,
                expected_responses=expected,
            )
            return
        except (DwarfCommandError, asyncio.TimeoutError) as exc:
            logger.warning(
                "dwarf.camera.v3_set_param_fallback_to_adjust",
                param_id=int(param_id),
                value=int(value),
                flag=int(flag),
                error=str(exc),
                error_type=type(exc).__name__,
            )

        adjust_request = ReqSetGeneralIntParam()
        adjust_request.param_id = int(param_id)
        adjust_request.value = int(value)
        await self._send_and_check(
            _MODULE_CAMERA_PARAMS,
            _CMD_PARAM_SET_GENERAL_INT,
            adjust_request,
            expected_responses=expected,
        )

    async def set_filter_position(self, position: int) -> str:
        async with self._get_filter_change_lock():
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
            index = state.filter_index
            if index is None:
                raise CaptureConfigurationError("No filter could be selected")

        options = await self._get_filter_options()
        if not options:
            raise CaptureConfigurationError("The device did not expose filter capabilities")

        if index < 0 or index >= len(options):
            logger.warning(
                "dwarf.camera.filter_index_out_of_range",
                index=index,
                total_options=len(options),
            )
            state.filter_index = None
            state.filter_name = ""
            await self._ensure_default_filter()
            index = state.filter_index
            if index is None or index < 0 or index >= len(options):
                raise CaptureConfigurationError("Selected filter is out of range")

        option = options[index]
        if not option.controllable:
            raise CaptureConfigurationError(
                f"Selected filter {option.label!r} cannot be controlled on this firmware"
            )

        current_label = (state.filter_name or "").strip().lower()
        desired_label = option.label.strip().lower()
        if (
            current_label == desired_label
            and state.filter_name
            and self.profile.filters.control_path != "v3-camera-param"
        ):
            state.applied_filter_name = state.filter_name
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
                raise CaptureConfigurationError(
                    f"Could not confirm selected filter {option.label!r}"
                ) from exc
            state.filter_index = None
            state.filter_name = ""
            await self._ensure_default_filter()
            if state.filter_index is None:
                raise CaptureConfigurationError(
                    f"Could not apply selected filter {option.label!r}"
                ) from exc

    async def _set_feature_param(
        self,
        feature: dict[str, Any],
        *,
        mode_index: int,
        index: int = 0,
        continue_value: float = 0.0,
        strict: bool = False,
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
            if strict:
                raise

    async def _configure_astro_capture(
        self,
        *,
        frames: int = 1,
        binning: tuple[int, int] | None = None,
    ) -> None:
        if self.simulation:
            return
        uses_v3 = self._uses_v3_protocol()
        config = await self._ensure_params_config()
        if config is None:
            raise CaptureConfigurationError(
                "Device parameter discovery failed; binning and frame count cannot be confirmed"
            )
        bin_x, bin_y = binning or (1, 1)
        try:
            bin_x = max(1, int(bin_x))
            bin_y = max(1, int(bin_y))
        except (TypeError, ValueError):
            bin_x, bin_y = (1, 1)

        if uses_v3:
            if (bin_x, bin_y) != (1, 1):
                raise CaptureConfigurationError(
                    f"{self.profile.display_name} V3 astronomy capture currently supports only "
                    "1x1 binning"
                )
            frames = max(1, int(frames))
            requested_gain = self.camera_state.requested_gain
            if requested_gain is None:
                requested_gain = int(self.profile.camera.min_gain_db)
            # Probe live exposure/gain support before touching the persisted
            # quick set. Mini firmware can reject 16700 with code -1 and must
            # use the complete 11041 tuple instead. Firmware which accepts the
            # live writes needs them applied again *after* 11041: a DWARF 3
            # Astro capture otherwise reloaded its stale 15-second value when
            # 11005 was dispatched despite a requested/acknowledged 1 second.
            live_parameters_applied = True
            try:
                await self._apply_v3_astro_exposure_gain(
                    self.camera_state.duration, int(requested_gain)
                )
            except DwarfCommandError as exc:
                # Keep this adaptive instead of branching on model names so V3
                # firmware variants on DWARF 2/3 can fall back safely.
                if exc.code != -1:
                    raise
                live_parameters_applied = False
                self._v3_live_parameters_supported = False
                self.camera_state.applied_duration = self.camera_state.duration
                self.camera_state.applied_gain_value = int(requested_gain)
                logger.warning(
                    "dwarf.camera.v3_live_parameters_unsupported",
                    model=self.profile.model_id,
                    command_id=exc.command_id,
                    code=exc.code,
                    fallback="quick_set_11041",
                )
            else:
                self._v3_live_parameters_supported = True
            await self._apply_v3_astro_quick_set(
                self.camera_state.duration,
                int(requested_gain),
                frames,
            )
            if live_parameters_applied:
                await self._apply_v3_astro_exposure_gain(
                    self.camera_state.duration, int(requested_gain)
                )
                try:
                    await self._set_v3_astro_frame_count(frames)
                except DwarfCommandError as exc:
                    if exc.code != -1:
                        raise
                    logger.warning(
                        "dwarf.camera.v3_frame_count_command_unsupported",
                        model=self.profile.model_id,
                        command_id=exc.command_id,
                        code=exc.code,
                        fallback="quick_set_11041",
                    )
            self.camera_state.applied_bin = (1, 1)
            self.camera_state.applied_frame_count = frames
            logger.info(
                "dwarf.camera.v3_astro_params_applied",
                exposure=self.camera_state.duration,
                gain=int(requested_gain),
                frames=frames,
                binning=(1, 1),
            )
            return

        async def _set_feature_by_label(feature_name: str, label_tokens: tuple[str, ...]) -> None:
            feature = self._find_feature_param(feature_name)
            if feature is None:
                if uses_v3:
                    logger.debug(
                        "dwarf.camera.feature_param_missing_optional",
                        name=feature_name,
                        device="dwarfmini",
                    )
                else:
                    logger.warning("dwarf.camera.feature_param_missing", name=feature_name)
                raise CaptureConfigurationError(
                    f"Required capture parameter {feature_name!r} is unavailable"
                )
            options = self._extract_feature_options(feature)
            for mode_index, index, label, continue_value in options:
                lowered = label.strip().lower()
                if all(token in lowered for token in label_tokens):
                    await self._set_feature_param(
                        feature,
                        mode_index=mode_index or 0,
                        index=index,
                        continue_value=continue_value or 0.0,
                        strict=True,
                    )
                    return
            logger.warning(
                "dwarf.camera.feature_option_missing",
                feature=feature_name,
                label_tokens=label_tokens,
            )
            raise CaptureConfigurationError(
                f"Requested option {label_tokens!r} is unavailable for {feature_name!r}"
            )

        desired_fixed = (
            ("Astro display source", 0, 1, 0.0),
            ("Astro ai enhance", 0, 0, 0.0),
        )
        for name, mode_index, index, continue_value in desired_fixed:
            feature = self._find_feature_param(name)
            if feature is None:
                if uses_v3:
                    logger.debug(
                        "dwarf.camera.feature_param_missing_optional", name=name, device="dwarfmini"
                    )
                else:
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
                strict=True,
            )
        else:
            if uses_v3:
                logger.debug(
                    "dwarf.camera.feature_param_missing_optional",
                    name="Astro img_to_take",
                    device="dwarfmini",
                )
            else:
                logger.warning("dwarf.camera.feature_param_missing", name="Astro img_to_take")
            raise CaptureConfigurationError(
                "Frame-count control is unavailable; requested count cannot be confirmed"
            )
        self.camera_state.applied_bin = (bin_x, bin_y)
        self.camera_state.applied_frame_count = frames

    async def _set_v3_astro_frame_count(self, frames: int) -> None:
        """Apply the authoritative frame count used by the shared V3 API."""

        request = ReqSetGeneralIntParam()
        request.param_id = _V3_ASTRO_FRAME_COUNT_PARAM_ID
        request.value = max(1, int(frames))
        await self._send_and_check(
            _MODULE_CAMERA_PARAMS,
            _CMD_PARAM_SET_GENERAL_INT,
            request,
            timeout=3.0,
            expected_responses={
                (_MODULE_CAMERA_PARAMS, _CMD_NOTIFY_GENERAL_INT_PARAM): GeneralIntParam,
                (
                    protocol_pb2.ModuleId.MODULE_NOTIFY,
                    _CMD_NOTIFY_GENERAL_INT_PARAM,
                ): GeneralIntParam,
            },
            close_ws_on_timeout=False,
        )
        logger.info(
            "dwarf.camera.v3_astro_frame_count_applied",
            param_id=_V3_ASTRO_FRAME_COUNT_PARAM_ID,
            frames=request.value,
        )

    async def _start_astro_capture(
        self,
        *,
        timeout: float,
        force_on_dark_warning: bool = False,
    ) -> int:
        if self.simulation:
            return protocol_pb2.OK
        embeds_filter_in_start = self._uses_v3_protocol() and bool(
            self.profile.filters.labels
        )
        uses_v3_sentinel = self._uses_v3_protocol() and not embeds_filter_in_start
        if uses_v3_sentinel:
            # The observed sentinel is ir_index=-1 in the same request used by
            # filtered V3 devices. Retaining the full message allows the app's
            # force_start continuation path to work on filterless models too.
            request = astro_pb2.ReqCaptureRawLiveStacking()
            request.ir_index = -1
            logger.info(
                "dwarf.camera.astro_capture_start_options",
                ir_index=request.ir_index,
                force_start=request.force_start,
                protocol="v3",
            )
        else:
            request = astro_pb2.ReqCaptureRawLiveStacking()
        if embeds_filter_in_start:
            options = await self._get_filter_options()
            position = self.camera_state.filter_index
            if position is None and options:
                position = 0
                self.camera_state.filter_index = 0
                self.camera_state.filter_name = options[0].label
            if position is None or position < 0 or position >= len(options):
                raise CaptureConfigurationError(
                    f"No valid {self.profile.display_name} imaging filter is selected"
                )
            option = options[position]
            request.ir_index = int(option.index)
            # Do not pre-emptively force a capture when no recent GoTo exists.
            # CODE_ASTRO_NEED_GOTO is a non-fatal warning, while force_start
            # also bypasses the normal missing-dark response. On DWARF 3 that
            # caused a requested 1-second exposure to be silently replaced by
            # the nearest installed dark preset (15 seconds). Starting normally
            # lets the firmware return its dark warning so command 11050 can
            # explicitly continue with the requested exposure/gain combination.
            request.force_start = False
            logger.info(
                "dwarf.camera.astro_capture_start_options",
                filter=option.label,
                ir_index=request.ir_index,
                force_start=request.force_start,
            )
        evidence_before = self._capture_evidence_snapshot()
        self._capture_start_evidence_event.clear()
        if self._uses_v3_protocol():
            response_future = await self._begin_request(
                protocol_pb2.ModuleId.MODULE_ASTRO,
                protocol_pb2.DwarfCMD.CMD_ASTRO_START_CAPTURE_RAW_LIVE_STACKING,
                request,
                astro_pb2.ResAstroShooting,
            )
            # Let the reader process an immediate rejection, but do not hold the
            # Alpaca request open for the delayed completion response.
            await asyncio.sleep(0)
            if response_future.done():
                immediate_response = response_future.result()
                immediate_code = int(
                    getattr(immediate_response, "code", protocol_pb2.OK)
                )
                if not (
                    immediate_code in _ASTRO_FORCE_START_DARK_WARNING_CODES
                    and force_on_dark_warning
                    and not bool(getattr(request, "force_start", False))
                ):
                    return self._validate_astro_start_response(
                        immediate_response,
                        option=locals().get("option"),
                    )
            self._set_astro_capture_operation_state(
                _OperationState.RUNNING,
                source="start_11005_dispatch",
            )
            old_task = self._capture_start_response_task
            if old_task and not old_task.done():
                old_task.cancel()
            capture_id = self.camera_state.capture_id
            monitor_timeout = max(
                float(timeout),
                self.camera_state.duration
                * max(1, self.camera_state.requested_frame_count)
                + 60.0,
            )
            self._capture_start_response_task = asyncio.create_task(
                self._monitor_astro_start_response(
                    response_future,
                    capture_id=capture_id,
                    timeout=monitor_timeout,
                    option=locals().get("option"),
                    ir_index=int(getattr(request, "ir_index", -1)),
                    force_on_dark_warning=(
                        force_on_dark_warning
                        and not bool(getattr(request, "force_start", False))
                    ),
                )
            )
            logger.info(
                "dwarf.camera.astro_capture_dispatched",
                capture_id=capture_id,
                response_timeout=monitor_timeout,
            )
            return protocol_pb2.OK
        try:
            response = await self._send_command(
                protocol_pb2.ModuleId.MODULE_ASTRO,
                protocol_pb2.DwarfCMD.CMD_ASTRO_START_CAPTURE_RAW_LIVE_STACKING,
                request,
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "dwarf.camera.astro_capture_timeout",
                timeout=timeout,
            )
            if embeds_filter_in_start:
                evidence_timeout = max(
                    float(self.settings.capture_start_evidence_timeout_seconds),
                    0.1,
                )
                try:
                    await asyncio.wait_for(
                        self._capture_start_evidence_event.wait(),
                        timeout=evidence_timeout,
                    )
                except asyncio.TimeoutError:
                    pass
                if self._capture_evidence_snapshot() != evidence_before:
                    logger.warning(
                        "dwarf.camera.astro_capture_timeout_corroborated",
                        timeout=timeout,
                        evidence=self._capture_evidence_snapshot(),
                    )
                    self.camera_state.applied_filter_name = option.label
                    return protocol_pb2.OK
                self.camera_state.capture_phase = CapturePhase.UNKNOWN
                self.camera_state.last_error = "capture_start_unknown"
            raise
        return self._validate_astro_start_response(response, option=locals().get("option"))

    def _validate_astro_start_response(
        self,
        response: Message,
        *,
        option: FilterOption | None = None,
        command_id: int = protocol_pb2.DwarfCMD.CMD_ASTRO_START_CAPTURE_RAW_LIVE_STACKING,
    ) -> int:
        code = int(getattr(response, "code", protocol_pb2.OK))
        if code == protocol_pb2.OK:
            if option is not None:
                self.camera_state.applied_filter_name = option.label
            return code

        if code in _ASTRO_NON_FATAL_START_WARNING_CODES:
            logger.warning(
                "dwarf.camera.astro_capture_start_warning",
                module_id=protocol_pb2.ModuleId.MODULE_ASTRO,
                command_id=command_id,
                code=code,
                non_fatal=True,
            )
            if option is not None:
                self.camera_state.applied_filter_name = option.label
            return code

        if code == protocol_pb2.CODE_ASTRO_FUNCTION_BUSY:
            logger.warning(
                "dwarf.camera.astro_capture_busy",
                module_id=protocol_pb2.ModuleId.MODULE_ASTRO,
                command_id=command_id,
                code=code,
            )
        else:
            logger.warning(
                "dwarf.camera.astro_capture_unexpected_code",
                module_id=protocol_pb2.ModuleId.MODULE_ASTRO,
                command_id=command_id,
                code=code,
            )

        raise DwarfCommandError(
            protocol_pb2.ModuleId.MODULE_ASTRO,
            command_id,
            code,
        )

    async def _begin_astro_dark_warning_continuation(
        self,
        *,
        ir_index: int,
        reason: str,
        force_legacy: bool = False,
    ) -> tuple[asyncio.Future[Message], int]:
        if self.profile.model_id != "dwarf2" and not force_legacy:
            command_id = protocol_pb2.DwarfCMD.CMD_ASTRO_CONTINUE_SHOOTING
            logger.info(
                "dwarf.camera.astro_capture_continue",
                reason=reason,
                command_id=command_id,
                protocol_minimum="2.5",
            )
            future = await self._begin_request(
                protocol_pb2.ModuleId.MODULE_ASTRO,
                command_id,
                astro_pb2.ReqContinueShooting(),
                ComResponse,
            )
            return future, command_id

        command_id = (
            protocol_pb2.DwarfCMD.CMD_ASTRO_START_CAPTURE_RAW_LIVE_STACKING
        )
        retry_request = astro_pb2.ReqCaptureRawLiveStacking()
        retry_request.ir_index = ir_index
        retry_request.force_start = True
        logger.info(
            "dwarf.camera.astro_capture_force_retry",
            reason=reason,
            ir_index=ir_index,
            force_start=True,
        )
        future = await self._begin_request(
            protocol_pb2.ModuleId.MODULE_ASTRO,
            command_id,
            retry_request,
            ComResponse,
        )
        return future, command_id

    async def _monitor_astro_start_response(
        self,
        response_future: asyncio.Future[Message],
        *,
        capture_id: str | None,
        timeout: float,
        option: FilterOption | None,
        ir_index: int,
        force_on_dark_warning: bool,
    ) -> None:
        pending_command_id = (
            protocol_pb2.DwarfCMD.CMD_ASTRO_START_CAPTURE_RAW_LIVE_STACKING
        )
        try:
            response = await asyncio.wait_for(response_future, timeout=timeout)
            code = int(getattr(response, "code", protocol_pb2.OK))
            if code in _ASTRO_FORCE_START_DARK_WARNING_CODES:
                warning_reason = (
                    "dark_missing"
                    if code == protocol_pb2.CODE_ASTRO_DARK_NOT_FOUND
                    else "dark_temperature_mismatch"
                )
                logger.warning(
                    "dwarf.camera.astro_capture_dark_warning",
                    code=code,
                    reason=warning_reason,
                    action=("continue" if force_on_dark_warning else "fail"),
                    ir_index=ir_index,
                    exposure=getattr(response, "exp_name", None) or None,
                    gain=getattr(response, "gain", None),
                    resolution=getattr(response, "resolution", None),
                    filter_type=getattr(response, "filter_type", None),
                    temperature_threshold=getattr(
                        response, "temp_threshold", None
                    ),
                )
                if force_on_dark_warning:
                    # APK 3.4.1 uses command 11050 on protocol >=2.5. DWARF 2
                    # and older/unsupported implementations use the legacy
                    # force_start retry.
                    retry_future, pending_command_id = (
                        await self._begin_astro_dark_warning_continuation(
                            ir_index=ir_index,
                            reason=warning_reason,
                        )
                    )
                    response = await asyncio.wait_for(retry_future, timeout=timeout)
                    continue_code = int(getattr(response, "code", protocol_pb2.OK))
                    if (
                        pending_command_id
                        == protocol_pb2.DwarfCMD.CMD_ASTRO_CONTINUE_SHOOTING
                        and continue_code
                        in {
                            protocol_pb2.WS_PARSE_PROTOBUF_ERROR,
                            protocol_pb2.WS_INVAID_PARAM,
                        }
                    ):
                        logger.warning(
                            "dwarf.camera.astro_capture_continue_unsupported",
                            code=continue_code,
                            action="force_start_fallback",
                        )
                        retry_future, pending_command_id = (
                            await self._begin_astro_dark_warning_continuation(
                                ir_index=ir_index,
                                reason=warning_reason,
                                force_legacy=True,
                            )
                        )
                        response = await asyncio.wait_for(retry_future, timeout=timeout)
            code = self._validate_astro_start_response(
                response,
                option=option,
                command_id=pending_command_id,
            )
            logger.info(
                "dwarf.camera.astro_capture_response",
                capture_id=capture_id,
                code=code,
            )
        except asyncio.CancelledError:
            raise
        except asyncio.TimeoutError:
            self._ws_client.cancel_pending(
                protocol_pb2.ModuleId.MODULE_ASTRO,
                pending_command_id,
            )
            logger.warning(
                "dwarf.camera.astro_capture_response_timeout",
                capture_id=capture_id,
                timeout=timeout,
            )
        except Exception as exc:
            logger.warning(
                "dwarf.camera.astro_capture_response_failed",
                capture_id=capture_id,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            state = self.camera_state
            if state.capture_id == capture_id and state.image is None:
                state.last_error = str(exc) or type(exc).__name__
                state.capture_phase = CapturePhase.FAILED
                task = state.capture_task
                if task and not task.done():
                    task.cancel()
        finally:
            if self._capture_start_response_task is asyncio.current_task():
                self._capture_start_response_task = None

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
            state.dark_status = "unknown"
            logger.warning(
                "dwarf.camera.dark_library_unknown",
                reason="no_response",
                continue_without_darks=continue_without_darks,
            )
            if continue_without_darks:
                return False
            raise CaptureConfigurationError(
                "Dark-frame status is unknown; explicitly allow capture without darks to proceed"
            )
        if code == protocol_pb2.OK:
            state.dark_status = "ready"
            if previous_code != code:
                logger.info("dwarf.camera.dark_library_ready")
            if state.last_error == "dark_missing":
                state.last_error = None
            return True
        if code == protocol_pb2.CODE_ASTRO_DARK_NOT_FOUND:
            state.dark_status = "missing"
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
        state.dark_status = f"error:{code}"
        if continue_without_darks:
            state.last_error = f"dark_code:{code}"
            return False
        raise DwarfCommandError(
            protocol_pb2.ModuleId.MODULE_ASTRO,
            protocol_pb2.DwarfCMD.CMD_ASTRO_CHECK_GOT_DARK,
            code,
        )

    async def _start_photo_capture(self, *, timeout: float) -> bool:
        if self.simulation:
            return True
        request = ReqPhotoRaw()
        try:
            await self._send_and_check(
                protocol_pb2.ModuleId.MODULE_CAMERA_TELE,
                protocol_pb2.DwarfCMD.CMD_CAMERA_TELE_PHOTO_RAW,
                request,
                timeout=timeout,
            )
            return True
        except asyncio.TimeoutError:
            logger.warning(
                "dwarf.camera.photo_raw_timeout",
                timeout=timeout,
            )
            if self._is_dwarf_mini():
                return await self._start_photo_capture_fallback(timeout=5.0)
            raise
        except DwarfCommandError as exc:
            logger.warning(
                "dwarf.camera.photo_raw_failed",
                code=exc.code,
            )
            if self._is_dwarf_mini():
                return await self._start_photo_capture_fallback(timeout=5.0)
            raise

    async def _start_photo_capture_fallback(self, *, timeout: float) -> bool:
        request = ReqPhoto()
        try:
            await self._send_and_check(
                protocol_pb2.ModuleId.MODULE_CAMERA_TELE,
                protocol_pb2.DwarfCMD.CMD_CAMERA_TELE_PHOTOGRAPH,
                request,
                timeout=timeout,
            )
        except Exception as exc:  # pragma: no cover - hardware dependent
            logger.warning(
                "dwarf.camera.photo_fallback_failed",
                timeout=timeout,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return False
        else:
            logger.info("dwarf.camera.photo_fallback_started")
            return True

    async def _stop_astro_capture(self, *, strict: bool = False) -> None:
        if self.simulation:
            return
        try:
            request = astro_pb2.ReqStopCaptureRawLiveStacking()
            if self._uses_v3_protocol():
                start_task = self._capture_start_response_task
                if start_task and not start_task.done():
                    start_task.cancel()
                self._capture_start_response_task = None
                self._ws_client.cancel_pending(
                    protocol_pb2.ModuleId.MODULE_ASTRO,
                    protocol_pb2.DwarfCMD.CMD_ASTRO_START_CAPTURE_RAW_LIVE_STACKING,
                )
                stop_task = self._capture_stop_response_task
                if stop_task and not stop_task.done():
                    return
                self._set_astro_capture_operation_state(
                    _OperationState.STOPPING,
                    source="stop_11006_dispatch",
                )
                response_future = await self._begin_request(
                    protocol_pb2.ModuleId.MODULE_ASTRO,
                    protocol_pb2.DwarfCMD.CMD_ASTRO_STOP_CAPTURE_RAW_LIVE_STACKING,
                    request,
                    ComResponse,
                )
                self._capture_stop_response_task = asyncio.create_task(
                    self._monitor_astro_stop_response(response_future)
                )
                logger.info("dwarf.camera.astro_stop_dispatched")
                return
            await self._send_and_check(
                protocol_pb2.ModuleId.MODULE_ASTRO,
                protocol_pb2.DwarfCMD.CMD_ASTRO_STOP_CAPTURE_RAW_LIVE_STACKING,
                request,
            )
        except Exception as exc:  # pragma: no cover - hardware dependent
            logger.debug("dwarf.astro.stop_capture_failed", error=str(exc))
            if strict:
                raise CaptureConfigurationError("DWARF did not confirm capture abort") from exc

    def _apply_v3_device_state_info(self, response: Message) -> dict[str, Any]:
        """Apply the verified command-16405 task-center state snapshot."""

        parsed: dict[str, Any] = {
            "shooting_mode": int(getattr(response, "shooting_mode", 0)),
            "code": int(getattr(response, "code", 0)),
        }
        if parsed["shooting_mode"]:
            self._v3_device_state_mode = int(parsed["shooting_mode"])

        has_field = getattr(response, "HasField", None)
        has_tele = callable(has_field) and response.HasField("tele_camera_state_info")
        if has_tele:
            tele = response.tele_camera_state_info
            width = int(tele.resolution_width)
            height = int(tele.resolution_height)
            h_fov = float(tele.h_fov)
            v_fov = float(tele.v_fov)
            if width > 0:
                self.camera_state.reported_preview_width = width
                parsed["image_width"] = width
            if height > 0:
                self.camera_state.reported_preview_height = height
                parsed["image_height"] = height
            if h_fov:
                self.camera_state.reported_fv_width = h_fov
                parsed["h_fov"] = h_fov
            if v_fov:
                self.camera_state.reported_fv_height = v_fov
                parsed["v_fov"] = v_fov
            if tele.HasField("cmos_temperature") and tele.cmos_temperature.HasField(
                "temperature"
            ):
                cmos_temperature = tele.cmos_temperature
                temperature = int(cmos_temperature.temperature)
                self.camera_state.temperature_c = float(temperature)
                self.camera_state.last_temperature_time = time.time()
                self.camera_state.last_temperature_code = protocol_pb2.OK
                parsed["cmos_temperature"] = temperature
                parsed["cmos_temperature_camera_type"] = int(
                    cmos_temperature.camera_type
                )
            if tele.HasField("exclusive_state") and tele.exclusive_state.HasField(
                "capture_raw_state"
            ):
                capture_raw = tele.exclusive_state.capture_raw_state
                capture_state = int(capture_raw.state)
                parsed["capture_raw_state"] = capture_state
                parsed["capture_raw_camera_type"] = int(capture_raw.camera_type)
                self._set_astro_capture_operation_state(
                    capture_state,
                    source="device_state_16405",
                )

        has_device = callable(has_field) and response.HasField("device_state_info")
        if has_device and response.device_state_info.HasField("calibration_result"):
            calibration = response.device_state_info.calibration_result
            azimuth = float(calibration.azi)
            altitude = float(calibration.alt)
            parsed["calibration_result"] = {
                "azimuth": azimuth,
                "altitude": altitude,
            }
            # This snapshot carries no completion timestamp, so retain it for
            # diagnostics without treating it as proof that a newly started
            # calibration just completed.
            self._calibration_azimuth = azimuth
            self._calibration_altitude = altitude
            logger.info(
                "dwarf.telescope.calibration.snapshot",
                azimuth=azimuth,
                altitude=altitude,
                source="device_state_16405",
            )
        return parsed

    async def _query_astro_capture_operation_state(self) -> int | None:
        """Mirror the APK's 16405 whole-device state query for tele RAW state."""

        try:
            response = await self._send_request(
                _MODULE_DEVICE_CONFIG,
                _CMD_TASK_GET_DEVICE_STATE,
                ReqGetDeviceStateInfo(),
                ResGetDeviceStateInfo,
                timeout=5.0,
                suppress_timeout_warning=True,
                close_ws_on_timeout=False,
            )
        except Exception as exc:  # pragma: no cover - hardware dependent
            logger.debug(
                "dwarf.camera.astro_capture_state_query_failed",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return None
        parsed = self._apply_v3_device_state_info(response)
        value = parsed.get("capture_raw_state")
        if not isinstance(value, int):
            logger.debug(
                "dwarf.camera.astro_capture_state_query_missing",
                payload_hex=response.SerializeToString().hex(),
            )
            return None
        return value

    async def _wait_for_astro_capture_ready(self, *, timeout: float = 75.0) -> None:
        """Do not start while firmware is finalizing the preceding stack."""

        if not self._uses_v3_protocol():
            return
        current = self._astro_capture_operation_state
        if current is None or current in {_OperationState.IDLE, _OperationState.STOPPED}:
            return
        started = time.monotonic()
        logger.info(
            "dwarf.camera.astro_capture_ready_wait_started",
            state=current,
            timeout=timeout,
        )
        deadline = started + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                logger.warning(
                    "dwarf.camera.astro_capture_ready_wait_timeout",
                    state=self._astro_capture_operation_state,
                    timeout=timeout,
                )
                raise DwarfCommandError(
                    protocol_pb2.ModuleId.MODULE_ASTRO,
                    protocol_pb2.DwarfCMD.CMD_ASTRO_START_CAPTURE_RAW_LIVE_STACKING,
                    protocol_pb2.CODE_ASTRO_FUNCTION_BUSY,
                )
            try:
                await asyncio.wait_for(
                    self._astro_capture_ready_event.wait(),
                    timeout=min(2.0, remaining),
                )
            except asyncio.TimeoutError:
                await self._query_astro_capture_operation_state()
                continue
            logger.info(
                "dwarf.camera.astro_capture_ready_wait_finished",
                state=self._astro_capture_operation_state,
                elapsed_seconds=round(time.monotonic() - started, 3),
            )
            return

    async def _monitor_astro_stop_response(
        self, response_future: asyncio.Future[Message]
    ) -> None:
        state_task = asyncio.create_task(self._astro_capture_ready_event.wait())
        try:
            done, _pending = await asyncio.wait(
                {response_future, state_task},
                timeout=75.0,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if state_task in done and state_task.result():
                self._ws_client.cancel_pending(
                    protocol_pb2.ModuleId.MODULE_ASTRO,
                    protocol_pb2.DwarfCMD.CMD_ASTRO_STOP_CAPTURE_RAW_LIVE_STACKING,
                )
                logger.info(
                    "dwarf.camera.astro_stop_state_confirmed",
                    state=self._astro_capture_operation_state,
                )
            elif response_future in done:
                response = response_future.result()
                code = int(getattr(response, "code", protocol_pb2.OK))
                if code != protocol_pb2.OK:
                    raise DwarfCommandError(
                        protocol_pb2.ModuleId.MODULE_ASTRO,
                        protocol_pb2.DwarfCMD.CMD_ASTRO_STOP_CAPTURE_RAW_LIVE_STACKING,
                        code,
                    )
                logger.info("dwarf.camera.astro_stop_response", code=code)
            else:
                raise asyncio.TimeoutError
        except asyncio.CancelledError:
            raise
        except asyncio.TimeoutError:
            self._ws_client.cancel_pending(
                protocol_pb2.ModuleId.MODULE_ASTRO,
                protocol_pb2.DwarfCMD.CMD_ASTRO_STOP_CAPTURE_RAW_LIVE_STACKING,
            )
            logger.warning("dwarf.camera.astro_stop_response_timeout", timeout=75.0)
        except Exception as exc:
            logger.warning(
                "dwarf.camera.astro_stop_response_failed",
                error=str(exc),
                error_type=type(exc).__name__,
            )
        finally:
            if not state_task.done():
                state_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await state_task
            if self._capture_stop_response_task is asyncio.current_task():
                self._capture_stop_response_task = None

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

    @staticmethod
    def _parse_gain_label(label: str) -> int | None:
        text = str(label).strip()
        if not text:
            return None
        try:
            return int(round(float(text)))
        except (TypeError, ValueError):
            match = re.search(r"-?\d+(?:\.\d+)?", text)
            if not match:
                return None
            try:
                return int(round(float(match.group(0))))
            except (TypeError, ValueError):
                return None

    async def _get_gain_support_param(self) -> dict[str, Any] | None:
        if self.simulation:
            return None
        if self._gain_support_param is not None:
            return self._gain_support_param
        await self._ensure_params_config()
        if self._params_config is None:
            self._gain_support_param = None
            return None
        param = self._find_support_param_contains("gain", camera_name="tele")
        self._gain_support_param = param if isinstance(param, dict) else None
        return self._gain_support_param

    async def _get_gain_options(self) -> list[tuple[int, int]]:
        if self._gain_value_options is not None:
            return self._gain_value_options
        options: list[tuple[int, int]] = []
        param = await self._get_gain_support_param()
        if isinstance(param, dict):
            gear_mode = param.get("gearMode")
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
                        label_value = self._parse_gain_label(entry.get("name", ""))
                        if label_value is None:
                            continue
                        options.append((label_value, index_value))
        options.sort(key=lambda item: item[0])
        self._gain_value_options = options
        return options

    async def _gain_manual_mode_enabled(self) -> bool:
        if self._gain_manual_mode_supported is not None:
            return self._gain_manual_mode_supported
        param = await self._get_gain_support_param()
        if not isinstance(param, dict):
            self._gain_manual_mode_supported = True
            return True
        self._gain_manual_mode_supported = bool(param.get("hasAuto"))
        return self._gain_manual_mode_supported

    async def _resolve_gain_command(self, requested_gain: int) -> tuple[int, int]:
        options = await self._get_gain_options()
        if not options:
            clamped_index = max(0, min(requested_gain, 255))
            return requested_gain, clamped_index
        min_value = options[0][0]
        max_value = options[-1][0]
        clamped_gain = max(min_value, min(requested_gain, max_value))
        for value, index in options:
            if value == clamped_gain:
                return value, index
        value, index = min(options, key=lambda opt: (abs(opt[0] - clamped_gain), opt[0]))
        return value, index

    async def _ensure_gain_settings(self) -> None:
        if self.simulation:
            return
        state = self.camera_state
        gain_value = state.requested_gain
        if gain_value is None:
            return
        if self._uses_v3_protocol():
            selected = self._v3_selected_astro_preset
            if selected is None:
                selected = await self._select_v3_astro_preset(state.duration)
            state.applied_gain_index = selected.gain
            state.applied_gain_value = selected.gain
            if selected.gain != int(round(gain_value)):
                logger.info(
                    "dwarf.camera.gain_snapped",
                    requested_gain=gain_value,
                    applied_gain=selected.gain,
                    protocol="v3-astro-preset",
                )
            return
        try:
            requested_gain = int(round(gain_value))
        except (TypeError, ValueError):
            return
        resolved_gain, command_index = await self._resolve_gain_command(requested_gain)
        if self._gain_command_supported is False:
            raise CaptureConfigurationError(
                f"Gain control is unavailable; requested gain {requested_gain} was not applied"
            )
        if self._gain_command_supported is True and state.applied_gain_index == resolved_gain:
            return

        command_timeout = max(self.settings.camera_gain_command_timeout_seconds, 0.5)

        if await self._gain_manual_mode_enabled():
            try:
                await self._set_gain_mode_manual(timeout=command_timeout)
            except Exception as exc:  # pragma: no cover - hardware dependent
                logger.debug(
                    "dwarf.camera.gain_mode_set_failed",
                    requested_gain=resolved_gain,
                    command_index=command_index,
                    error=str(exc),
                    error_type=type(exc).__name__,
                )
                self._disable_gain_commands(resolved_gain, command_index=command_index)
                raise CaptureConfigurationError(
                    f"Could not enable manual gain for requested gain {requested_gain}"
                ) from exc

        try:
            await self._set_gain_index(command_index, timeout=command_timeout)
        except DwarfCommandError as exc:  # pragma: no cover - hardware dependent
            logger.warning(
                "dwarf.camera.gain_set_failed",
                requested_gain=resolved_gain,
                command_index=command_index,
                error_code=exc.code,
                module_id=exc.module_id,
                command_id=exc.command_id,
            )
            self._disable_gain_commands(resolved_gain, command_index=command_index)
            raise CaptureConfigurationError(
                f"DWARF rejected requested gain {requested_gain}"
            ) from exc
        except Exception as exc:  # pragma: no cover - hardware dependent
            logger.warning(
                "dwarf.camera.gain_set_error",
                requested_gain=resolved_gain,
                command_index=command_index,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            self._disable_gain_commands(resolved_gain, command_index=command_index)
            raise CaptureConfigurationError(
                f"Could not apply requested gain {requested_gain}"
            ) from exc

        if resolved_gain != requested_gain:
            logger.debug(
                "dwarf.camera.gain_snapped",
                requested_gain=requested_gain,
                applied_gain=resolved_gain,
                command_index=command_index,
            )

        state.applied_gain_index = resolved_gain
        state.applied_gain_value = resolved_gain
        self._gain_command_supported = True
        self._gain_last_skipped_value = None
        logger.info(
            "dwarf.camera.gain_applied",
            gain=resolved_gain,
            command_index=command_index,
        )

    def _disable_gain_commands(self, gain_value: int, *, command_index: int | None = None) -> None:
        if self._gain_command_supported is False:
            if self._gain_last_skipped_value != gain_value:
                logger.debug(
                    "dwarf.camera.gain_command_skipped",
                    requested_gain=gain_value,
                    command_index=command_index,
                )
                self._gain_last_skipped_value = gain_value
            return
        self._gain_command_supported = False
        self._gain_last_skipped_value = gain_value
        if not self._gain_command_warning_logged:
            logger.warning(
                "dwarf.camera.gain_commands_disabled",
                requested_gain=gain_value,
                command_index=command_index,
            )
            self._gain_command_warning_logged = True

    async def _set_gain_mode_manual(self, *, timeout: float | None = None) -> None:
        request = ReqSetGainMode()
        request.mode = 1
        effective_timeout = timeout if timeout is not None else 10.0
        await self._send_and_check(
            protocol_pb2.ModuleId.MODULE_CAMERA_TELE,
            protocol_pb2.DwarfCMD.CMD_CAMERA_TELE_SET_GAIN_MODE,
            request,
            timeout=effective_timeout,
            expected_responses=self._tele_param_expected_responses(),
        )

    async def _set_gain_index(self, index: int, *, timeout: float | None = None) -> None:
        request = ReqSetGain()
        request.index = index
        effective_timeout = timeout if timeout is not None else 10.0
        await self._send_and_check(
            protocol_pb2.ModuleId.MODULE_CAMERA_TELE,
            protocol_pb2.DwarfCMD.CMD_CAMERA_TELE_SET_GAIN,
            request,
            timeout=effective_timeout,
            expected_responses=self._tele_param_expected_responses(),
        )

    async def _refresh_capture_baseline(self, *, capture_kind: str) -> None:
        state = self.camera_state
        if capture_kind == "photo":
            await self._refresh_ftp_baseline(capture_kind=capture_kind)
            await self._refresh_album_baseline(media_type=1)
        else:
            # Walking every astronomy directory over FTP can take longer than
            # NINA's 10-second StartExposure timeout. Astro retrieval already
            # rejects files older than last_start_time, so the cached entry is
            # a sufficient stale-file guard and keeps StartExposure responsive.
            state.pending_ftp_baseline = state.last_ftp_entry
            # The HTTP album query is cheap and provides the only reliable
            # baseline when firmware FTP is unavailable.  Without it an old
            # album item can be mistaken for the exposure NINA just requested.
            await self._refresh_album_baseline(media_type=4)

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

    async def _refresh_album_baseline(self, *, media_type: int = 1) -> None:
        state = self.camera_state
        if self.simulation:
            state.pending_album_baseline = state.last_album_mod_time
            return
        mod_time, entry = await self._get_latest_album_entry(media_type=media_type)
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
            entries = await self._http_client.list_album_media_infos(
                media_type=media_type, page_size=1
            )
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

    @staticmethod
    def _album_astro_src_dir(entry: dict[str, Any]) -> str | None:
        details = entry.get("astroImageDetails")
        if isinstance(details, dict):
            src_dir = details.get("srcDir")
            if isinstance(src_dir, str) and src_dir.strip():
                return src_dir.strip()
        src_dir = entry.get("srcDir")
        if isinstance(src_dir, str) and src_dir.strip():
            return src_dir.strip()
        return None

    async def _download_album_astro_fits(
        self, state: CameraState, entry: dict[str, Any]
    ) -> bool:
        src_dir = self._album_astro_src_dir(entry)
        if not src_dir:
            logger.warning(
                "dwarf.camera.astro_album_src_dir_missing",
                capture_id=state.capture_id,
                keys=sorted(entry.keys()),
            )
            return False
        try:
            fits_entries = await self._http_client.list_astro_fits(src_dir)
        except Exception as exc:  # pragma: no cover - hardware dependent
            logger.warning(
                "dwarf.camera.astro_fits_list_failed",
                capture_id=state.capture_id,
                src_dir=src_dir,
                error=str(exc),
            )
            return False
        candidates = [
            item
            for item in fits_entries
            if not bool(item.get("isFailed"))
            and isinstance(item.get("filePath") or item.get("url"), str)
        ]
        if not candidates:
            logger.warning(
                "dwarf.camera.astro_fits_list_empty",
                capture_id=state.capture_id,
                src_dir=src_dir,
                total=len(fits_entries),
            )
            return False
        fits_entry = candidates[-1]
        file_id = str(fits_entry.get("filePath") or fits_entry.get("url"))
        try:
            content = await self._http_client.fetch_media_file(file_id)
            frame = self._decode_capture_content(file_id, content)
        except Exception as exc:  # pragma: no cover - hardware dependent
            logger.warning(
                "dwarf.camera.astro_fits_download_failed",
                capture_id=state.capture_id,
                src_dir=src_dir,
                path=file_id,
                error=str(exc),
            )
            return False
        self._store_frame(state, frame, time.time())
        state.retrieved_file_path = file_id
        logger.info(
            "dwarf.camera.astro_fits_selected",
            capture_id=state.capture_id,
            src_dir=src_dir,
            path=file_id,
            size_bytes=len(content),
        )
        return True

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
        state.capture_phase = CapturePhase.PROCESSING
        astro_mode = state.capture_mode == "astro"
        image_captured = state.image is not None
        if not self.simulation:
            state.capture_phase = CapturePhase.TRANSFERRING
            ftp_success = False
            if astro_mode:
                ftp_task = asyncio.create_task(self._attempt_ftp_capture(state))
                progress_task = asyncio.create_task(self._capture_frame_complete_event.wait())
                trigger = "ftp"
                try:
                    exposure_budget = state.duration * max(
                        1, state.requested_frame_count
                    )
                    deadline = time.monotonic() + max(exposure_budget + 55.0, 58.0)
                    while True:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            trigger = "capture_timeout"
                            break
                        active = {progress_task}
                        if not ftp_task.done():
                            active.add(ftp_task)
                        done, _pending = await asyncio.wait(
                            active,
                            timeout=remaining,
                            return_when=asyncio.FIRST_COMPLETED,
                        )
                        if not done:
                            trigger = "capture_timeout"
                            break
                        if progress_task in done and progress_task.result():
                            trigger = "stacking_progress"
                            break
                        if ftp_task in done and ftp_task.result():
                            trigger = "ftp"
                            break
                        # FTP timeout is not capture completion. Firmware may
                        # still be exposing/stacking and will notify us later.
                        trigger = "waiting_after_ftp_timeout"
                    logger.info(
                        "dwarf.camera.astro_capture_stop_triggered",
                        capture_id=state.capture_id,
                        trigger=trigger,
                        requested_frames=state.requested_frame_count,
                        current_count=state.progress_current_count,
                        stacked_count=state.progress_stacked_count,
                        retrieved_file=state.retrieved_file_path,
                    )
                    await self._stop_astro_capture()
                    ftp_success = await ftp_task
                finally:
                    if not progress_task.done():
                        progress_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await progress_task
                    if not ftp_task.done():
                        ftp_task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await ftp_task
            else:
                await asyncio.sleep(max(state.duration * max(1, state.requested_frame_count), 0.1))
                ftp_success = await self._attempt_ftp_capture(state)
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
        state.capture_phase = CapturePhase.READY if image_captured else CapturePhase.FAILED

    async def _attempt_ftp_capture(self, state: CameraState) -> bool:
        baseline = state.pending_ftp_baseline
        exposure_budget = state.duration * max(1, state.requested_frame_count)
        timeout = max(exposure_budget + 55.0, 58.0)
        try:
            capture = await self._ftp_client.wait_for_new_photo(
                baseline,
                timeout=timeout,
                capture_kind=state.capture_mode,
                not_before=(
                    state.last_start_time - 5.0 if state.last_start_time is not None else None
                ),
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
        state.retrieved_file_path = capture.entry.path
        state.last_ftp_entry = capture.entry
        state.pending_ftp_baseline = capture.entry
        logger.info(
            "dwarf.camera.ftp_capture_selected",
            capture_id=state.capture_id,
            path=capture.entry.path,
            directory=capture.entry.directory,
            filename=capture.entry.name,
            timestamp=capture.entry.timestamp,
            size_bytes=len(capture.content),
            baseline=None if baseline is None else baseline.path,
            exposure_started_at=state.last_start_time,
            requested_duration=state.duration,
            firmware_duration=state.reported_duration,
        )
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
            if is_new and not self._album_entry_is_recent(
                latest_entry, not_before=state.last_start_time
            ):
                logger.warning(
                    "dwarf.camera.album_stale_entry_rejected",
                    capture_id=state.capture_id,
                    file=file_id,
                    modification_time=mod_time,
                    exposure_started_at=state.last_start_time,
                )
                is_new = False
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

        if state.capture_mode == "astro" and await self._download_album_astro_fits(
            state, entry
        ):
            state.pending_album_baseline = state.last_album_mod_time
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

    @staticmethod
    def _album_entry_is_recent(
        entry: dict[str, Any], *, not_before: float | None
    ) -> bool:
        if not_before is None:
            return True
        raw = entry.get("modificationTime")
        try:
            timestamp = float(raw)
            if timestamp > 10_000_000_000:
                timestamp /= 1000.0
            if timestamp > 1_000_000_000:
                return timestamp >= not_before - 5.0
        except (TypeError, ValueError):
            pass
        identifier = DwarfSession._album_entry_file(entry) or ""
        match = re.search(r"(20\d{6})[-_](\d{6})", identifier)
        if match:
            try:
                timestamp = time.mktime(
                    datetime.strptime("".join(match.groups()), "%Y%m%d%H%M%S").timetuple()
                )
                return timestamp >= not_before - 5.0
            except ValueError:
                pass
        # With no temporal evidence, a changed path is insufficient proof.
        return False

    def _store_frame(self, state: CameraState, frame: np.ndarray, timestamp: float) -> None:
        if not np.issubdtype(frame.dtype, np.integer) and not np.issubdtype(
            frame.dtype, np.floating
        ):
            raise ValueError(f"unsupported_frame_dtype:{frame.dtype}")
        state.image = frame
        state.frame_height, state.frame_width = frame.shape[:2]
        state.image_timestamp = timestamp
        state.last_end_time = timestamp
        state.start_time = None
        state.last_error = None
        if frame.size:
            frame_min = float(np.min(frame))
            frame_max = float(np.max(frame))
            logger.info(
                "dwarf.camera.frame_stored",
                width=state.frame_width,
                height=state.frame_height,
                dtype=str(frame.dtype),
                pixel_min=frame_min,
                pixel_max=frame_max,
                pixel_mean=float(np.mean(frame)),
                uniform=frame_min == frame_max,
                saturated_12bit=frame_min == frame_max == 4095.0,
                source_format=state.source_format,
            )

    def _decode_capture_content(self, identifier: str, content: bytes) -> np.ndarray:
        name = identifier.rsplit("/", 1)[-1]
        lower = name.lower()
        if lower.endswith((".fits", ".fit")):
            self.camera_state.source_format = "FITS"
            self.camera_state.source_bit_depth = 16
            return self._decode_fits(content)
        self.camera_state.source_format = "JPEG"
        self.camera_state.source_bit_depth = 8
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
        if frame.dtype not in (np.uint8, np.uint16):
            raise ValueError(f"unsupported_jpeg_dtype:{frame.dtype}")
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
        if self._uses_v3_protocol():
            request = ReqGetUserInfinityPos()
            try:
                response = await self._send_request(
                    protocol_pb2.ModuleId.MODULE_FOCUS,
                    _CMD_FOCUS_GET_USER_INFINITY_POS,
                    request,
                    ResUserInfinityPos,
                    timeout=3.0,
                    suppress_timeout_warning=True,
                    close_ws_on_timeout=False,
                )
                if isinstance(response, ResUserInfinityPos):
                    focus_position = int(getattr(response, "pos", state.position))
                    state.position = max(0, min(focus_position, 20000))
                    state.last_update = time.time()
            except Exception as exc:  # pragma: no cover - hardware dependent
                logger.debug(
                    "dwarf.focus.v3_init_failed",
                    error=str(exc),
                    error_type=type(exc).__name__,
                )

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
        command_direction = self._focus_command_direction(delta)
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
            prefer_single_step = steps <= 10 or self._is_dwarf_mini()
            fallback_reason = None
            if steps > 10 and (last_update_age is None or last_update_age > 5.0):
                fallback_reason = (
                    "stale_focus_telemetry" if last_update_age is not None else "no_focus_telemetry"
                )
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
                request.direction = command_direction
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
                start_request.direction = command_direction
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
            tolerance = max(0, int(getattr(self.settings, "focuser_target_tolerance_steps", 0)))
            if (
                not prefer_single_step
                and tolerance > 0
                and abs(target - state.position) > tolerance
            ):
                try:
                    await self._focus_nudge_to_target(target, tolerance=tolerance)
                except Exception:
                    logger.warning(
                        "dwarf.focus.nudge_failed",
                        target=target,
                        position=state.position,
                        exc_info=True,
                    )
                state.position = max(0, min(state.position, 20000))
            state.is_moving = False
            logger.info(
                "dwarf.focus.move.completed",
                position=state.position,
                received_update=received_update,
            )

    async def _focus_nudge_to_target(self, target: int, *, tolerance: int) -> None:
        state = self.focuser_state
        max_iterations = 60
        for _ in range(max_iterations):
            error = target - state.position
            if abs(error) <= tolerance:
                return

            step_direction = 1 if error > 0 else -1
            request = ReqManualSingleStepFocus()
            request.direction = self._focus_command_direction(error)
            self._focus_update_event.clear()
            await self._send_and_check(
                protocol_pb2.ModuleId.MODULE_FOCUS,
                protocol_pb2.DwarfCMD.CMD_FOCUS_MANUAL_SINGLE_STEP_FOCUS,
                request,
            )
            try:
                await asyncio.wait_for(self._focus_update_event.wait(), timeout=0.6)
            except asyncio.TimeoutError:
                state.position = max(0, min(state.position + step_direction, 20000))
                state.last_update = time.time()
            finally:
                self._focus_update_event.clear()

        logger.warning(
            "dwarf.focus.nudge_incomplete",
            target=target,
            position=state.position,
        )

    @staticmethod
    def _focus_command_direction(delta: int) -> int:
        """Translate signed focus delta into DWARF direction codes.

        The DWARF focus protocol uses 0 for "far" focus (increasing the
        reported focus position) and 1 for "near" focus (decreasing the
        reported focus position)."""

        if delta < 0:
            return 1
        return 0

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
_session_lock: asyncio.Lock | None = None
_session_lock_loop: asyncio.AbstractEventLoop | None = None
_session_settings: Settings | None = None


def _get_session_lock() -> asyncio.Lock:
    global _session_lock, _session_lock_loop
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.get_event_loop_policy().get_event_loop()
    lock = _session_lock
    if lock is None or _session_lock_loop is not loop:
        lock = asyncio.Lock()
        _session_lock = lock
        _session_lock_loop = loop
    return lock


def configure_session(settings: Settings) -> None:
    global _session_settings, _session
    _session_settings = settings
    if _session is not None:
        ws_minor_version, ws_device_id = _resolve_ws_protocol_profile(settings)
        _session.settings = settings
        _session.profile = get_device_profile(settings.dwarf_device_model)
        _session.simulation = settings.force_simulation
        _session._observer_latitude = settings.site_latitude
        _session._observer_longitude = settings.site_longitude
        _session._ws_client.set_client_id(resolve_ws_client_id(settings))
        _session._ws_client.minor_version = ws_minor_version
        _session._ws_client.device_id = ws_device_id
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
        _session._master_lock_acquired = False
        _session._ws_bootstrapped = False
        _session._time_synced = settings.force_simulation
        _session._params_config = None
        _session._filter_options = None
        _session._v3_device_state_event = None
        _session._v3_device_state_mode = None
        _session._v3_device_state_detail = None
        _session._v3_device_state_path = None
        _session._v3_mode_change = None
        _session._v3_observation_state = None
        _session._v3_exposure_progress = None
        _session._v3_device_config_bytes = None


async def get_session() -> DwarfSession:
    global _session
    if _session is None:
        lock = _get_session_lock()
        async with lock:
            if _session is None:
                settings = _session_settings or Settings()
                _session = DwarfSession(settings)
    return _session


async def shutdown_session() -> None:
    global _session, _session_lock, _session_lock_loop
    session = _session
    if session is None:
        return
    # Detach first so a session containing loop-bound locks/tasks can never be
    # reused by a subsequent GUI server thread, even if shutdown encounters an
    # error while talking to a disappearing device.
    _session = None
    _session_lock = None
    _session_lock_loop = None
    await session.shutdown()
