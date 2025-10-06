from __future__ import annotations

import asyncio
import contextlib
import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ..dwarf.session import get_session
from .utils import alpaca_response, bind_request_context, resolve_parameter
router = APIRouter(dependencies=[Depends(bind_request_context)])

_MAX_MANUAL_AXIS_RATE = 4.0

@dataclass
class TelescopeState:
    connected: bool = False
    right_ascension: float = 0.0
    declination: float = 0.0
    target_ra: float | None = None
    target_dec: float | None = None
    slewing: bool = False
    tracking: bool = True
    last_command_time: float = field(default_factory=time.time)
    altitude: float = 0.0
    azimuth: float = 0.0
    declination_rate: float = 0.0
    right_ascension_rate: float = 0.0
    guide_rate_ra: float = 0.5
    guide_rate_dec: float = 0.5
    side_of_pier: int = 0
    tracking_rate: int = 0
    site_latitude: float = 0.0
    site_longitude: float = 0.0
    site_elevation: float = 0.0
    slew_settle_time: int = 0
    using_simulation: bool = True
    custom_utc_offset_seconds: float | None = None
    slew_task: asyncio.Task[None] | None = field(default=None, repr=False)
    motion_update_time: float = field(default_factory=time.time, repr=False)


state = TelescopeState()


def _parse_float(value: str | float) -> float:
    if isinstance(value, float):
        return value
    normalized = value.replace(",", ".")
    return float(normalized)


async def _resolve_with_aliases(
    request: Request,
    names: tuple[str, ...],
    *preferred_values: str | float | None,
) -> str | float:
    for candidate in preferred_values:
        if candidate is not None:
            return candidate

    missing_error: HTTPException | None = None
    for name in names:
        try:
            return await resolve_parameter(request, name, str)
        except HTTPException as exc:
            if exc.status_code == 400 and exc.detail == f"{name} parameter required":
                missing_error = exc
                continue
            raise

    if missing_error is not None:
        raise HTTPException(status_code=400, detail=f"{names[0]} parameter required") from missing_error
    raise HTTPException(status_code=400, detail=f"{names[0]} parameter required")


@router.get("/connected")
def get_connected():
    return alpaca_response(value=state.connected)


@router.put("/connected")
async def put_connected(
    request: Request,
    Connected_query: bool | None = Query(None, alias="Connected", description="Set connection state"),
    Simulation_query: bool | None = Query(None, alias="Simulation", description="Override simulation mode"),
):
    value = await resolve_parameter(request, "Connected", bool, Connected_query)
    session = await get_session()

    simulation_override: bool | None = None
    if Simulation_query is not None:
        simulation_override = await resolve_parameter(request, "Simulation", bool, Simulation_query)
    else:
        try:
            simulation_override = await resolve_parameter(request, "Simulation", bool)
        except HTTPException as exc:
            if exc.detail != "Simulation parameter required":
                raise
            simulation_override = None

    if value:
        if simulation_override is not None:
            session.simulation = simulation_override
        await session.acquire("telescope")
        state.using_simulation = session.is_simulated
    else:
        state.motion_update_time = time.time()
        if not session.is_simulated:
            with contextlib.suppress(Exception):
                await session.telescope_stop_axis(0)
            with contextlib.suppress(Exception):
                await session.telescope_stop_axis(1)
        if state.slew_task and not state.slew_task.done():
            state.slew_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await state.slew_task
        state.slew_task = None
        state.slewing = False
        state.right_ascension_rate = 0.0
        state.declination_rate = 0.0
        await session.release("telescope")
        if simulation_override is not None:
            session.simulation = simulation_override
        state.using_simulation = session.is_simulated
    state.connected = value
    return alpaca_response()


@router.get("/description")
def get_description():
    return alpaca_response(value="DWARF 3 Telescope")


@router.get("/name")
def get_name():
    return alpaca_response(value="DWARF 3 Telescope")


@router.get("/driverversion")
def get_driver_version():
    return alpaca_response(value="0.1.0")


@router.get("/interfaceversion")
def get_interface_version():
    return alpaca_response(value=3)


@router.get("/rightascension")
def get_right_ascension():
    return alpaca_response(value=state.right_ascension)


@router.get("/declination")
def get_declination():
    return alpaca_response(value=state.declination)


@router.get("/altitude")
def get_altitude():
    _process_motion()
    return alpaca_response(value=state.altitude)


@router.get("/azimuth")
def get_azimuth():
    _process_motion()
    return alpaca_response(value=state.azimuth)


@router.get("/athome")
def get_at_home():
    return alpaca_response(value=False)


@router.get("/atpark")
def get_at_park():
    return alpaca_response(value=False)


@router.get("/utcdate")
def get_utc_date():
    current = datetime.now(timezone.utc)
    if state.custom_utc_offset_seconds is not None:
        current += timedelta(seconds=state.custom_utc_offset_seconds)
    return alpaca_response(value=current.isoformat())


@router.put("/utcdate")
async def set_utc_date(
    request: Request,
    UTCDate_query: str | None = Query(None, alias="UTCDate"),
    Date_query: str | None = Query(None, alias="Date"),
):
    raw = await resolve_parameter(request, "UTCDate", str, UTCDate_query, Date_query)
    normalized = raw.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid UTCDate format") from exc
    if parsed.tzinfo is None:
        local_tz = datetime.now().astimezone().tzinfo or timezone.utc
        parsed = parsed.replace(tzinfo=local_tz)
    parsed = parsed.astimezone(timezone.utc)
    now_utc = datetime.now(timezone.utc)
    offset = (parsed - now_utc).total_seconds()
    state.custom_utc_offset_seconds = offset if abs(offset) > 1e-6 else None
    return alpaca_response()


@router.get("/declinationrate")
def get_declination_rate():
    return alpaca_response(value=state.declination_rate)


@router.get("/guideratedeclination")
def get_guide_rate_declination():
    return alpaca_response(value=state.guide_rate_dec)


@router.get("/guideraterightascension")
def get_guide_rate_right_ascension():
    return alpaca_response(value=state.guide_rate_ra)


@router.get("/ispulseguiding")
def get_is_pulse_guiding():
    return alpaca_response(value=False)


@router.get("/rightascensionrate")
def get_right_ascension_rate():
    return alpaca_response(value=state.right_ascension_rate)


@router.get("/sideofpier")
def get_side_of_pier():
    return alpaca_response(value=state.side_of_pier)


@router.get("/siderealtime")
def get_sidereal_time():
    lst = _local_sidereal_time(datetime.now(timezone.utc), state.site_longitude)
    return alpaca_response(value=lst)


@router.get("/targetdeclination")
def get_target_declination():
    value = state.target_dec if state.target_dec is not None else state.declination
    return alpaca_response(value=value)


@router.get("/targetrightascension")
def get_target_right_ascension():
    value = state.target_ra if state.target_ra is not None else state.right_ascension
    return alpaca_response(value=value)


@router.get("/trackingrate")
def get_tracking_rate():
    return alpaca_response(value=state.tracking_rate)


@router.get("/alignmentmode")
def get_alignment_mode():
    return alpaca_response(value=1)


@router.get("/aperturearea")
def get_aperture_area():
    # Approximate 70mm aperture (m^2)
    return alpaca_response(value=0.0038)


@router.get("/aperturediameter")
def get_aperture_diameter():
    return alpaca_response(value=0.07)


@router.get("/driverinfo")
def get_driver_info():
    return alpaca_response(value="DWARF 3 Alpaca Telescope Stub")


@router.get("/doesrefraction")
def get_does_refraction():
    return alpaca_response(value=False)


@router.get("/equatorialsystem")
def get_equatorial_system():
    return alpaca_response(value=2)


@router.get("/focallength")
def get_focal_length():
    return alpaca_response(value=0.4)


@router.get("/siteelevation")
def get_site_elevation():
    return alpaca_response(value=state.site_elevation)


@router.get("/slewsettletime")
def get_slew_settle_time():
    return alpaca_response(value=state.slew_settle_time)


@router.get("/supportedactions")
def get_supported_actions():
    return alpaca_response(value=[])


@router.put("/slewtocoordinatesasync")
async def slew_to_coordinates_async(
    request: Request,
    RightAscension_query: float | None = Query(None, alias="RightAscension", ge=0.0, le=24.0),
    Declination_query: float | None = Query(None, alias="Declination", ge=-90.0, le=90.0),
):
    if not state.connected:
        raise HTTPException(status_code=400, detail="Telescope not connected")
    ra = await resolve_parameter(request, "RightAscension", float, RightAscension_query)
    dec = await resolve_parameter(request, "Declination", float, Declination_query)
    session = await get_session()
    state.using_simulation = session.is_simulated
    state.target_ra = ra
    state.target_dec = dec
    state.slewing = True
    state.last_command_time = time.time()
    if session.is_simulated:
        state.right_ascension_rate = (ra - state.right_ascension) / 2.0
        state.declination_rate = (dec - state.declination) / 2.0
    else:
        await session.telescope_slew_to_coordinates(ra, dec)
        state.right_ascension_rate = 0.0
        state.declination_rate = 0.0
        if state.slew_task and not state.slew_task.done():
            state.slew_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await state.slew_task
        state.slew_task = asyncio.create_task(_complete_hardware_slew(ra, dec))
    return alpaca_response()


@router.put("/abortslew")
async def abort_slew():
    session = await get_session()
    if not session.is_simulated:
        await session.telescope_abort_slew()
    if state.slew_task and not state.slew_task.done():
        state.slew_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await state.slew_task
    state.slew_task = None
    state.slewing = False
    state.right_ascension_rate = 0.0
    state.declination_rate = 0.0
    return alpaca_response()


@router.get("/slewing")
def get_slewing():
    _process_motion()
    return alpaca_response(value=state.slewing)


@router.put("/tracking")
async def set_tracking(
    request: Request,
    Tracking_query: bool | None = Query(None, alias="Tracking"),
):
    tracking = await resolve_parameter(request, "Tracking", bool, Tracking_query)
    state.tracking = tracking
    return alpaca_response()


@router.get("/tracking")
def get_tracking():
    return alpaca_response(value=state.tracking)


@router.get("/canpark")
def get_canpark():
    return alpaca_response(value=False)


@router.get("/canfindhome")
def get_can_find_home():
    return alpaca_response(value=False)


@router.get("/canpulseguide")
def get_can_pulseguide():
    return alpaca_response(value=False)


@router.get("/cansetdeclinationrate")
def get_can_set_declination_rate():
    return alpaca_response(value=False)


@router.get("/cansetguiderates")
def get_can_set_guiderates():
    return alpaca_response(value=False)


@router.get("/cansetpark")
def get_can_set_park():
    return alpaca_response(value=False)


@router.get("/cansetpierside")
def get_can_set_pierside():
    return alpaca_response(value=False)


@router.get("/cansetrightascensionrate")
def get_can_set_ra_rate():
    return alpaca_response(value=False)


@router.get("/cansettracking")
def get_can_set_tracking():
    return alpaca_response(value=True)


@router.get("/canslew")
def get_can_slew():
    return alpaca_response(value=True)


@router.get("/canslewasync")
def get_can_slew_async():
    return alpaca_response(value=True)


@router.get("/canslewaltaz")
def get_can_slew_altaz():
    return alpaca_response(value=False)


@router.get("/canslewaltazasync")
def get_can_slew_altaz_async():
    return alpaca_response(value=False)


@router.get("/cansync")
def get_can_sync():
    return alpaca_response(value=False)


@router.get("/cansyncaltaz")
def get_can_sync_altaz():
    return alpaca_response(value=False)


@router.get("/canunpark")
def get_can_unpark():
    return alpaca_response(value=False)


@router.get("/canmoveaxis")
def get_can_move_axis(Axis: int = Query(..., ge=0, le=2)):
    return alpaca_response(value=Axis in {0, 1})


@router.get("/axisrates/{Axis}")
def get_axis_rates(Axis: int):
    if Axis not in {0, 1, 2}:
        raise HTTPException(status_code=400, detail="Invalid axis")
    if Axis in {0, 1}:
        rates = [{"Minimum": -4.0, "Maximum": 4.0}]
    else:
        rates = [{"Minimum": 0.0, "Maximum": 0.0}]
    return alpaca_response(value=rates)


@router.get("/axisrates")
def get_axis_rates_query(
    Axis: int = Query(..., ge=0, le=2),
):
    return get_axis_rates(Axis)


@router.put("/moveaxis")
async def move_axis(
    request: Request,
    Axis_query: int | None = Query(None, alias="Axis", ge=0, le=2),
    Rate_query: float | None = Query(None, alias="Rate"),
):
    if not state.connected:
        raise HTTPException(status_code=400, detail="Telescope not connected")

    axis = await resolve_parameter(request, "Axis", int, Axis_query)
    if axis not in {0, 1}:
        raise HTTPException(status_code=400, detail="Axis must be 0 or 1")

    rate = await resolve_parameter(request, "Rate", float, Rate_query)
    if not -_MAX_MANUAL_AXIS_RATE <= rate <= _MAX_MANUAL_AXIS_RATE:
        raise HTTPException(status_code=400, detail="Rate exceeds supported range")

    session = await get_session()
    state.using_simulation = session.is_simulated
    _process_motion()
    state.motion_update_time = time.time()

    if state.slew_task and not state.slew_task.done():
        state.slew_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await state.slew_task
    state.slew_task = None
    state.target_ra = None
    state.target_dec = None

    if axis == 0:
        state.right_ascension_rate = rate
    else:
        state.declination_rate = rate

    has_motion = abs(state.right_ascension_rate) > 0.0 or abs(state.declination_rate) > 0.0
    state.slewing = has_motion

    if session.is_simulated:
        _update_alt_az()
        return alpaca_response()

    if abs(rate) < 1e-6:
        await session.telescope_stop_axis(axis)
    else:
        await session.telescope_move_axis(axis, rate)

    return alpaca_response()


@router.get("/trackingrates")
def get_tracking_rates():
    return alpaca_response(value=[0])


@router.get("/sitelatitude")
def get_site_latitude():
    return alpaca_response(value=state.site_latitude)


@router.put("/sitelatitude")
async def set_site_latitude(
    request: Request,
    Latitude_query: str | float | None = Query(None, alias="Latitude"),
    SiteLatitude_query: str | float | None = Query(None, alias="SiteLatitude"),
):
    raw = await _resolve_with_aliases(
        request,
        ("SiteLatitude", "Latitude"),
        SiteLatitude_query,
        Latitude_query,
    )
    value = _parse_float(raw)
    if not -90.0 <= value <= 90.0:
        raise HTTPException(status_code=400, detail="Latitude out of range")
    state.site_latitude = value
    _update_alt_az()
    return alpaca_response()


@router.get("/sitelongitude")
def get_site_longitude():
    return alpaca_response(value=state.site_longitude)


@router.put("/sitelongitude")
async def set_site_longitude(
    request: Request,
    Longitude_query: str | float | None = Query(None, alias="Longitude"),
    SiteLongitude_query: str | float | None = Query(None, alias="SiteLongitude"),
):
    raw = await _resolve_with_aliases(
        request,
        ("SiteLongitude", "Longitude"),
        SiteLongitude_query,
        Longitude_query,
    )
    value = _parse_float(raw)
    if not -180.0 <= value <= 180.0:
        raise HTTPException(status_code=400, detail="Longitude out of range")
    state.site_longitude = value
    _update_alt_az()
    return alpaca_response()


@router.put("/siteelevation")
async def set_site_elevation(
    request: Request,
    Elevation_query: str | float | None = Query(None, alias="Elevation"),
    SiteElevation_query: str | float | None = Query(None, alias="SiteElevation"),
):
    raw = await _resolve_with_aliases(
        request,
        ("SiteElevation", "Elevation"),
        SiteElevation_query,
        Elevation_query,
    )
    value = _parse_float(raw)
    state.site_elevation = value
    return alpaca_response()


def _process_motion() -> None:
    if not state.using_simulation:
        _update_alt_az()
        return

    now = time.time()
    delta = max(0.0, now - state.motion_update_time)
    state.motion_update_time = now

    if state.slewing and state.target_ra is not None and state.target_dec is not None:
        duration = 2.0
        elapsed = now - state.last_command_time
        if elapsed >= duration:
            state.right_ascension = state.target_ra
            state.declination = state.target_dec
            state.slewing = False
            state.right_ascension_rate = 0.0
            state.declination_rate = 0.0
        else:
            t = elapsed / duration
            state.right_ascension = state.right_ascension + (state.target_ra - state.right_ascension) * t
            state.declination = state.declination + (state.target_dec - state.declination) * t
        _update_alt_az()
        return

    if delta > 0.0:
        if abs(state.right_ascension_rate) > 0.0:
            state.right_ascension = (state.right_ascension + (state.right_ascension_rate * delta) / 15.0) % 24.0
        if abs(state.declination_rate) > 0.0:
            state.declination = max(-90.0, min(90.0, state.declination + state.declination_rate * delta))

    state.altitude = state.declination
    state.azimuth = (state.right_ascension * 15.0) % 360.0


async def _complete_hardware_slew(target_ra: float, target_dec: float) -> None:
    try:
        await asyncio.sleep(2.0)
    except asyncio.CancelledError:
        return
    state.right_ascension = target_ra
    state.declination = target_dec
    state.slewing = False
    _update_alt_az()


def _update_alt_az() -> None:
    altitude, azimuth = _compute_alt_az(
        state.right_ascension,
        state.declination,
        state.site_latitude,
        state.site_longitude,
    )
    state.altitude = altitude
    state.azimuth = azimuth


def _compute_alt_az(
    ra_hours: float,
    dec_degrees: float,
    latitude: float,
    longitude: float,
) -> tuple[float, float]:
    if latitude == 0.0 and longitude == 0.0:
        # Default to simple mapping if no site data has been provided.
        return dec_degrees, (ra_hours * 15.0) % 360.0

    lst = _local_sidereal_time(datetime.now(timezone.utc), longitude)
    hour_angle_hours = (lst - ra_hours) % 24.0
    hour_angle = math.radians(hour_angle_hours * 15.0)
    dec_rad = math.radians(dec_degrees)
    lat_rad = math.radians(latitude)

    sin_alt = (
        math.sin(dec_rad) * math.sin(lat_rad)
        + math.cos(dec_rad) * math.cos(lat_rad) * math.cos(hour_angle)
    )
    sin_alt = max(-1.0, min(1.0, sin_alt))
    alt_rad = math.asin(sin_alt)

    cos_az = (
        math.sin(dec_rad) - math.sin(alt_rad) * math.sin(lat_rad)
    ) / (math.cos(alt_rad) * math.cos(lat_rad) + 1e-9)
    sin_az = -math.sin(hour_angle) * math.cos(dec_rad) / (math.cos(alt_rad) + 1e-9)
    az_rad = math.atan2(sin_az, cos_az)

    altitude = math.degrees(alt_rad)
    azimuth = (math.degrees(az_rad) + 360.0) % 360.0
    return altitude, azimuth


def _local_sidereal_time(dt: datetime, longitude_deg: float) -> float:
    jd = _julian_date(dt)
    T = (jd - 2451545.0) / 36525.0
    gst = (
        280.46061837
        + 360.98564736629 * (jd - 2451545.0)
        + 0.000387933 * T ** 2
        - (T ** 3) / 38710000.0
    )
    gst_hours = (gst % 360.0) / 15.0
    lst = (gst_hours + longitude_deg / 15.0) % 24.0
    return lst


def _julian_date(dt: datetime) -> float:
    year = dt.year
    month = dt.month
    day = dt.day + (dt.hour + dt.minute / 60.0 + dt.second / 3600.0) / 24.0
    if month <= 2:
        year -= 1
        month += 12
    A = year // 100
    B = 2 - A + A // 4
    jd = int(365.25 * (year + 4716)) + int(30.6001 * (month + 1)) + day + B - 1524.5
    return jd
