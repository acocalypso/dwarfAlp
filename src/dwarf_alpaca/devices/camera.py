from __future__ import annotations

import asyncio
import base64
import time
from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ..dwarf.session import get_session
from ..dwarf.ws_client import DwarfCommandError
from ..proto import protocol_pb2
from .utils import alpaca_response, bind_request_context, resolve_parameter

router = APIRouter(dependencies=[Depends(bind_request_context)])
logger = structlog.get_logger(__name__)

CAMERA_STATE_IDLE = 0
CAMERA_STATE_EXPOSING = 2
CAMERA_STATE_READOUT = 3
CAMERA_STATE_READY = 4

SENSOR_TYPE_RGGB = 2


@dataclass(frozen=True)
class SensorProfile:
    name: str
    resolution_x: int
    resolution_y: int
    bits_per_pixel: int
    ad_converter_bits: int
    max_binning: int
    pixel_size_um: float
    max_gain_db: float
    min_exposure_s: float
    max_exposure_s: float
    electrons_per_adu: list[float]
    full_well_capacity_e: list[float]
    raw_format: str
    bayer_pattern: str
    read_noise_range_e: tuple[float, float] | None = None
    peak_qe: float | None = None


IMX678_PROFILE = SensorProfile(
    name="Sony IMX678 STARVIS 2",
    resolution_x=3856,
    resolution_y=2176,
    bits_per_pixel=16,
    ad_converter_bits=12,
    max_binning=2,
    pixel_size_um=2.0,
    max_gain_db=200.0,
    min_exposure_s=0.00001,
    max_exposure_s=120.0,
    electrons_per_adu=[2.75],
    full_well_capacity_e=[11270.0],
    raw_format="SRGGB12",
    bayer_pattern="RGGB",
    read_noise_range_e=(0.6, 2.7),
    peak_qe=0.83,
)


@dataclass
class CameraState:
    connected: bool = False
    bin_x: int = 1
    bin_y: int = 1
    sensor_width: int = IMX678_PROFILE.resolution_x
    sensor_height: int = IMX678_PROFILE.resolution_y
    subframe_start_x: int = 0
    subframe_start_y: int = 0
    subframe_width: int = IMX678_PROFILE.resolution_x
    subframe_height: int = IMX678_PROFILE.resolution_y
    frame_count: int = 1
    max_bin_x: int = IMX678_PROFILE.max_binning
    max_bin_y: int = IMX678_PROFILE.max_binning
    pixel_size_x: float = IMX678_PROFILE.pixel_size_um
    pixel_size_y: float = IMX678_PROFILE.pixel_size_um
    has_shutter: bool = True
    gain: int = 0
    gain_min: int = 0
    gain_max: int = int(IMX678_PROFILE.max_gain_db)
    offset: int = 0
    offset_min: int = 0
    offset_max: int = 255
    ccd_temperature: float = 25.0
    heatsink_temperature: float = 25.0


state = CameraState()


def _ensure_connected() -> None:
    if not state.connected:
        raise HTTPException(status_code=400, detail="Camera not connected")


def _format_timestamp(timestamp: float | None) -> str:
    if timestamp is None:
        return ""
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


def _gain_steps() -> list[int]:
    if state.gain_max == state.gain_min:
        return [state.gain_min]
    increments = np.linspace(state.gain_min, state.gain_max, num=7).tolist()
    return sorted({int(round(value)) for value in increments})


_IMAGE_TYPE_MAP: dict[np.dtype, int] = {
    np.dtype(np.int16): 1,
    np.dtype(np.int32): 2,
    np.dtype(np.float64): 3,
}

_IMAGE_TYPE_NAMES = {
    0: "Unknown",
    1: "Int16",
    2: "Int32",
    3: "Double",
    4: "Single",
    5: "UInt64",
    6: "Byte",
    7: "Int64",
    8: "UInt16",
}


def _resolve_image_array(image: np.ndarray) -> tuple[np.ndarray, int]:
    dtype = image.dtype
    if dtype in _IMAGE_TYPE_MAP:
        return image, _IMAGE_TYPE_MAP[dtype]
    if np.issubdtype(dtype, np.integer):
        if image.size == 0:
            coerced = image.astype(np.int16, copy=False)
            return coerced, _IMAGE_TYPE_MAP[np.dtype(np.int16)]
        if np.issubdtype(dtype, np.signedinteger):
            min_value = int(image.min())
            max_value = int(image.max())
            if np.iinfo(np.int16).min <= min_value <= max_value <= np.iinfo(np.int16).max:
                coerced = image.astype(np.int16, copy=False)
                return coerced, _IMAGE_TYPE_MAP[np.dtype(np.int16)]
            if np.iinfo(np.int32).min <= min_value <= max_value <= np.iinfo(np.int32).max:
                coerced = image.astype(np.int32, copy=False)
                return coerced, _IMAGE_TYPE_MAP[np.dtype(np.int32)]
        else:
            max_value = int(image.max())
            if max_value <= np.iinfo(np.int32).max:
                coerced = image.astype(np.int32, copy=False)
                return coerced, _IMAGE_TYPE_MAP[np.dtype(np.int32)]
        coerced = image.astype(np.float64, copy=False)
        return coerced, _IMAGE_TYPE_MAP[np.dtype(np.float64)]
    if np.issubdtype(dtype, np.floating):
        coerced = image.astype(np.float64, copy=False)
        return coerced, _IMAGE_TYPE_MAP[np.dtype(np.float64)]
    raise HTTPException(status_code=500, detail="Unsupported image data type")


@router.get("/description")
def get_description():
    return alpaca_response(value="DWARF 3 Camera")


@router.get("/name")
def get_name():
    return alpaca_response(value="DWARF 3 Camera")


@router.get("/driverversion")
def get_driver_version():
    return alpaca_response(value="0.1.0")


@router.get("/driverinfo")
def get_driver_info():
    return alpaca_response(value="DWARF Alpaca Camera Driver")


@router.get("/interfaceversion")
def get_interface_version():
    return alpaca_response(value=2)


@router.get("/supportedactions")
def get_supported_actions():
    return alpaca_response(value=[])


@router.get("/canabortexposure")
def get_can_abort_exposure():
    return alpaca_response(value=True)


@router.get("/canstopexposure")
def get_can_stop_exposure():
    return alpaca_response(value=True)


@router.get("/canasymmetricbin")
def get_can_asymmetric_bin():
    return alpaca_response(value=False)


@router.get("/canfastreadout")
def get_can_fast_readout():
    return alpaca_response(value=False)


@router.get("/cangetcoolerpower")
def get_can_get_cooler_power():
    return alpaca_response(value=False)


@router.get("/cansetccdtemperature")
def get_can_set_ccd_temperature():
    return alpaca_response(value=False)


@router.get("/hasshutter")
def get_has_shutter():
    return alpaca_response(value=state.has_shutter)


@router.get("/cameraxsize")
def get_camera_x_size():
    return alpaca_response(value=state.sensor_width)


@router.get("/cameraysize")
def get_camera_y_size():
    return alpaca_response(value=state.sensor_height)


@router.get("/maxbinx")
def get_max_bin_x():
    return alpaca_response(value=state.max_bin_x)


@router.get("/maxbiny")
def get_max_bin_y():
    return alpaca_response(value=state.max_bin_y)


@router.get("/pixelsizex")
def get_pixel_size_x():
    return alpaca_response(value=state.pixel_size_x)


@router.get("/pixelsizey")
def get_pixel_size_y():
    return alpaca_response(value=state.pixel_size_y)


@router.get("/exposuremax")
def get_exposure_max():
    return alpaca_response(value=IMX678_PROFILE.max_exposure_s)


@router.get("/exposuremin")
def get_exposure_min():
    return alpaca_response(value=IMX678_PROFILE.min_exposure_s)


@router.get("/exposureresolution")
def get_exposure_resolution():
    return alpaca_response(value=0.000001)


@router.get("/readoutmode")
def get_readout_mode():
    return alpaca_response(value=0)


@router.get("/readoutmodes")
def get_readout_modes():
    return alpaca_response(value=["Normal"])


@router.get("/gainmin")
def get_gain_min():
    return alpaca_response(value=state.gain_min)


@router.get("/gainmax")
def get_gain_max():
    return alpaca_response(value=state.gain_max)


@router.get("/gain")
def get_gain():
    return alpaca_response(value=state.gain)


@router.put("/gain")
async def set_gain(request: Request, Gain: int | None = Query(None, alias="Gain")):
    value = await resolve_parameter(request, "Gain", int, Gain)
    if value < state.gain_min or value > state.gain_max:
        raise HTTPException(status_code=400, detail="Gain out of range")
    state.gain = value
    return alpaca_response()


@router.get("/offsetmin")
def get_offset_min():
    return alpaca_response(value=state.offset_min)


@router.get("/offsetmax")
def get_offset_max():
    return alpaca_response(value=state.offset_max)


@router.get("/offset")
def get_offset():
    return alpaca_response(value=state.offset)


@router.put("/offset")
async def set_offset(request: Request, Offset: int | None = Query(None, alias="Offset")):
    value = await resolve_parameter(request, "Offset", int, Offset)
    if value < state.offset_min or value > state.offset_max:
        raise HTTPException(status_code=400, detail="Offset out of range")
    state.offset = value
    return alpaca_response()


@router.get("/sensortype")
def get_sensor_type():
    return alpaca_response(value=SENSOR_TYPE_RGGB)


@router.get("/sensorname")
def get_sensor_name():
    return alpaca_response(value=IMX678_PROFILE.name)


@router.get("/electronsperadu")
def get_electrons_per_adu():
    value = IMX678_PROFILE.electrons_per_adu[0] if IMX678_PROFILE.electrons_per_adu else 0.0
    return alpaca_response(value=value)


@router.get("/fullwellcapacity")
def get_full_well_capacity():
    value = IMX678_PROFILE.full_well_capacity_e[0] if IMX678_PROFILE.full_well_capacity_e else 0.0
    return alpaca_response(value=value)


@router.get("/maxadu")
def get_max_adu():
    max_value = (1 << IMX678_PROFILE.ad_converter_bits) - 1
    return alpaca_response(value=max_value)


@router.get("/bayeroffsetx")
def get_bayer_offset_x():
    return alpaca_response(value=0)


@router.get("/bayeroffsety")
def get_bayer_offset_y():
    return alpaca_response(value=0)


@router.get("/ccdtemperature")
async def get_ccd_temperature():
    session = await get_session()
    runtime = session.camera_state
    temperature = runtime.temperature_c
    if temperature is not None:
        state.ccd_temperature = float(temperature)
    return alpaca_response(value=state.ccd_temperature)


@router.get("/cooleron")
def get_cooler_on():
    return alpaca_response(value=False)


@router.put("/cooleron")
def set_cooler_on(CoolerOn: bool = Query(..., alias="CoolerOn")):
    if CoolerOn:
        raise HTTPException(status_code=400, detail="Cooler control not supported")
    return alpaca_response()


@router.get("/coolerpower")
def get_cooler_power():
    return alpaca_response(value=0.0)


@router.get("/heatsinktemperature")
async def get_heatsink_temperature():
    session = await get_session()
    runtime = session.camera_state
    temperature = runtime.temperature_c
    if temperature is not None:
        state.heatsink_temperature = float(temperature)
    return alpaca_response(value=state.heatsink_temperature)


@router.get("/connected")
def get_connected():
    return alpaca_response(value=state.connected)


@router.put("/connected")
async def put_connected(
    request: Request,
    Connected_query: bool | None = Query(None, alias="Connected"),
):
    value = await resolve_parameter(request, "Connected", bool, Connected_query)
    session = await get_session()
    if value:
        await session.acquire("camera")
        try:
            await session.camera_connect()
        except Exception:
            await session.release("camera")
            raise
    else:
        try:
            await session.camera_disconnect()
        finally:
            await session.release("camera")
    runtime = session.camera_state
    state.connected = runtime.connected
    return alpaca_response()


@router.get("/camerastate")
async def get_camera_state():
    if not state.connected:
        return alpaca_response(value=CAMERA_STATE_IDLE)
    session = await get_session()
    runtime = session.camera_state
    if runtime.start_time is None:
        if runtime.image is not None:
            return alpaca_response(value=CAMERA_STATE_READY)
        return alpaca_response(value=CAMERA_STATE_IDLE)

    elapsed = time.time() - runtime.start_time
    if elapsed < runtime.duration:
        return alpaca_response(value=CAMERA_STATE_EXPOSING)
    if runtime.image is None:
        return alpaca_response(value=CAMERA_STATE_READOUT)
    return alpaca_response(value=CAMERA_STATE_READY)


@router.get("/lastexposureduration")
async def get_last_exposure_duration():
    session = await get_session()
    runtime = session.camera_state
    if runtime.last_end_time is not None and runtime.last_start_time is not None:
        return alpaca_response(value=max(runtime.last_end_time - runtime.last_start_time, 0.0))
    if runtime.start_time is not None:
        return alpaca_response(value=max(time.time() - runtime.start_time, 0.0))
    return alpaca_response(value=runtime.duration)


@router.get("/lastexposurestarttime")
async def get_last_exposure_start_time():
    session = await get_session()
    runtime = session.camera_state
    return alpaca_response(value=_format_timestamp(runtime.last_start_time))


@router.get("/imagetimestamp")
async def get_image_timestamp():
    session = await get_session()
    runtime = session.camera_state
    timestamp = runtime.image_timestamp if runtime.image_timestamp is not None else runtime.last_end_time
    return alpaca_response(value=_format_timestamp(timestamp))


@router.put("/startexposure")
async def start_exposure(
    request: Request,
    Duration: float | None = Query(None, alias="Duration"),
    Light: bool | None = Query(None, alias="Light"),
    ContinueWithoutDark: bool | None = Query(None, alias="ContinueWithoutDark"),
    FrameCount: int | None = Query(None, alias="FrameCount"),
    NumFrames: int | None = Query(None, alias="NumFrames"),
    ImageCount: int | None = Query(None, alias="ImageCount"),
):
    _ensure_connected()
    session = await get_session()
    duration_value = await resolve_parameter(request, "Duration", float, Duration)
    if duration_value <= 0.0:
        raise HTTPException(status_code=400, detail="Duration must be greater than zero")
    light_value = await resolve_parameter(request, "Light", bool, Light)
    continue_without_dark = (
        ContinueWithoutDark
        if ContinueWithoutDark is not None
        else session.settings.allow_continue_without_darks
    )
    frame_count_value: int | None = None
    for name, raw in (
        ("FrameCount", FrameCount),
        ("NumFrames", NumFrames),
        ("ImageCount", ImageCount),
    ):
        if raw is None:
            continue
        resolved = await resolve_parameter(request, name, int, raw)
        frame_count_value = resolved
        break
    if frame_count_value is not None:
        if frame_count_value < 1:
            raise HTTPException(status_code=400, detail="Frame count must be at least 1")
        state.frame_count = frame_count_value
    else:
        frame_count_value = max(state.frame_count, 1)
        state.frame_count = frame_count_value
    client = request.client
    redacted_headers = [
        (
            name,
            value if name.lower() not in {"authorization", "cookie"} else "***REDACTED***",
        )
        for name, value in request.headers.items()
    ]
    logger.info(
        "alpaca.camera.start_exposure_request",
        request_url=str(request.url),
        client_host=getattr(client, "host", None),
        client_port=getattr(client, "port", None),
        raw_duration=Duration,
        raw_light=Light,
        raw_continue_without_dark=ContinueWithoutDark,
        raw_frame_count=(FrameCount if FrameCount is not None else NumFrames if NumFrames is not None else ImageCount),
        resolved_duration=duration_value,
        resolved_light=light_value,
        continue_without_dark=continue_without_dark,
        frame_count=frame_count_value,
        query_params=dict(request.query_params),
        headers=redacted_headers,
    )
    session.camera_state.requested_gain = state.gain
    session.camera_state.requested_bin = (state.bin_x, state.bin_y)
    session.camera_state.requested_frame_count = frame_count_value
    try:
        await session.camera_start_exposure(
            duration_value,
            light_value,
            continue_without_darks=continue_without_dark,
        )
    except DwarfCommandError as exc:
        if exc.code == protocol_pb2.CODE_ASTRO_FUNCTION_BUSY:
            raise HTTPException(
                status_code=409,
                detail=(
                    "DWARF is still processing a previous astro capture. "
                    "Wait for it to finish or abort it before retrying."
                ),
            ) from exc
        raise HTTPException(
            status_code=502,
            detail=(
                "DWARF command "
                f"{exc.module_id}:{exc.command_id} failed with code {exc.code}"
            ),
        ) from exc
    except asyncio.TimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail="Timed out while waiting for DWARF to start the exposure.",
        ) from exc
    return alpaca_response()


@router.put("/stopexposure")
async def stop_exposure():
    session = await get_session()
    await session.camera_abort_exposure()
    return alpaca_response()


@router.put("/abortexposure")
async def abort_exposure():
    session = await get_session()
    await session.camera_abort_exposure()
    return alpaca_response()


@router.get("/imageready")
async def get_image_ready():
    session = await get_session()
    return alpaca_response(value=session.camera_state.image is not None)


@router.get("/imagebytes")
async def get_image_bytes():
    session = await get_session()
    image = await session.camera_readout()
    if image is None:
        raise HTTPException(status_code=400, detail="Image not ready")
    processed_image, type_code = _resolve_image_array(image)
    bytes_data = processed_image.tobytes()
    height, width = processed_image.shape[:2]
    runtime = session.camera_state
    if runtime.frame_width and not session.simulation:
        state.sensor_width = runtime.frame_width
    else:
        state.sensor_width = max(state.sensor_width, width)
    if runtime.frame_height and not session.simulation:
        state.sensor_height = runtime.frame_height
    else:
        state.sensor_height = max(state.sensor_height, height)
    state.subframe_width = min(state.subframe_width, state.sensor_width - state.subframe_start_x)
    state.subframe_height = min(state.subframe_height, state.sensor_height - state.subframe_start_y)
    if state.subframe_width <= 0:
        state.subframe_start_x = 0
        state.subframe_width = state.sensor_width
    if state.subframe_height <= 0:
        state.subframe_start_y = 0
        state.subframe_height = state.sensor_height
    encoded = base64.b64encode(bytes_data).decode()
    metadata = {
        "FrameSize": len(bytes_data),
        "ImageElementType": type_code,
        "ImageElementTypeName": _IMAGE_TYPE_NAMES.get(type_code, "Unknown"),
        "TransmissionElementType": type_code,
        "TransmissionElementTypeName": _IMAGE_TYPE_NAMES.get(type_code, "Unknown"),
        "Rank": 2,
        "Dim1": height,
        "Dim2": width,
        "BayerOffsetX": 0,
        "BayerOffsetY": 0,
        "BayerPattern": "RGGB",
    }
    return alpaca_response(value={"ImageBytes": encoded, **metadata})


@router.get("/imagearray")
async def get_image_array():
    session = await get_session()
    image = await session.camera_readout()
    if image is None:
        raise HTTPException(status_code=400, detail="Image not ready")
    processed_image, type_code = _resolve_image_array(image)
    payload = alpaca_response(value=processed_image.tolist())
    payload["Type"] = type_code
    payload["Rank"] = processed_image.ndim
    payload["Dimensions"] = list(processed_image.shape)
    payload["TypeName"] = _IMAGE_TYPE_NAMES.get(type_code, "Unknown")
    return payload


@router.get("/imagearrayvariant")
async def get_image_array_variant():
    session = await get_session()
    image = await session.camera_readout()
    if image is None:
        raise HTTPException(status_code=400, detail="Image not ready")
    processed_image, type_code = _resolve_image_array(image)
    payload = alpaca_response(value=processed_image.tolist())
    payload["Type"] = type_code
    payload["Rank"] = processed_image.ndim
    payload["Dimensions"] = list(processed_image.shape)
    payload["TypeName"] = _IMAGE_TYPE_NAMES.get(type_code, "Unknown")
    return payload


@router.get("/numx")
def get_num_x():
    return alpaca_response(value=state.subframe_width)


@router.get("/numy")
def get_num_y():
    return alpaca_response(value=state.subframe_height)


@router.put("/numx")
async def set_num_x(request: Request, NumX: int | None = Query(None, alias="NumX")):
    value = await resolve_parameter(request, "NumX", int, NumX)
    if value < 1:
        raise HTTPException(status_code=400, detail="NumX must be at least 1")
    max_width = state.sensor_width - state.subframe_start_x
    if value > max_width:
        raise HTTPException(status_code=400, detail="NumX exceeds sensor width")
    state.subframe_width = value
    return alpaca_response()


@router.put("/numy")
async def set_num_y(request: Request, NumY: int | None = Query(None, alias="NumY")):
    value = await resolve_parameter(request, "NumY", int, NumY)
    if value < 1:
        raise HTTPException(status_code=400, detail="NumY must be at least 1")
    max_height = state.sensor_height - state.subframe_start_y
    if value > max_height:
        raise HTTPException(status_code=400, detail="NumY exceeds sensor height")
    state.subframe_height = value
    return alpaca_response()


@router.get("/startx")
def get_start_x():
    return alpaca_response(value=state.subframe_start_x)


@router.put("/startx")
async def set_start_x(request: Request, StartX: int | None = Query(None, alias="StartX")):
    value = await resolve_parameter(request, "StartX", int, StartX)
    if value < 0:
        raise HTTPException(status_code=400, detail="StartX must be non-negative")
    if value >= state.sensor_width:
        raise HTTPException(status_code=400, detail="StartX exceeds sensor width")
    state.subframe_start_x = value
    max_width = state.sensor_width - state.subframe_start_x
    state.subframe_width = min(state.subframe_width, max_width)
    return alpaca_response()


@router.get("/starty")
def get_start_y():
    return alpaca_response(value=state.subframe_start_y)


@router.put("/starty")
async def set_start_y(request: Request, StartY: int | None = Query(None, alias="StartY")):
    value = await resolve_parameter(request, "StartY", int, StartY)
    if value < 0:
        raise HTTPException(status_code=400, detail="StartY must be non-negative")
    if value >= state.sensor_height:
        raise HTTPException(status_code=400, detail="StartY exceeds sensor height")
    state.subframe_start_y = value
    max_height = state.sensor_height - state.subframe_start_y
    state.subframe_height = min(state.subframe_height, max_height)
    return alpaca_response()


@router.get("/binx")
def get_bin_x():
    return alpaca_response(value=state.bin_x)


@router.put("/binx")
async def set_bin_x(request: Request, BinX: int | None = Query(None, alias="BinX")):
    value = await resolve_parameter(request, "BinX", int, BinX)
    if value < 1:
        raise HTTPException(status_code=400, detail="BinX must be at least 1")
    if value > state.max_bin_x:
        raise HTTPException(status_code=400, detail="BinX exceeds maximum")
    state.bin_x = value
    return alpaca_response()


@router.get("/biny")
def get_bin_y():
    return alpaca_response(value=state.bin_y)


@router.put("/biny")
async def set_bin_y(request: Request, BinY: int | None = Query(None, alias="BinY")):
    value = await resolve_parameter(request, "BinY", int, BinY)
    if value < 1:
        raise HTTPException(status_code=400, detail="BinY must be at least 1")
    if value > state.max_bin_y:
        raise HTTPException(status_code=400, detail="BinY exceeds maximum")
    state.bin_y = value
    return alpaca_response()


@router.get("/cameragains")
def get_camera_gains():
    return alpaca_response(value=_gain_steps())


@router.get("/gains")
def get_available_gains():
    return alpaca_response(value=_gain_steps())

