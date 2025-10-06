from __future__ import annotations

from dataclasses import dataclass, field

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ..dwarf.session import get_session
from .utils import alpaca_response, bind_request_context, resolve_parameter

router = APIRouter(dependencies=[Depends(bind_request_context)])
logger = structlog.get_logger(__name__)


@dataclass
class FilterWheelState:
    connected: bool = False
    position: int | None = None
    names: list[str] = field(default_factory=list)
    focus_offsets: list[int] = field(default_factory=list)

    def set_names(self, names: list[str]) -> None:
        self.names = names
        self.focus_offsets = [0] * len(names)
        if self.position is not None and (self.position < 0 or self.position >= len(names)):
            self.position = None


state = FilterWheelState()


async def preload_filters() -> None:
    """Fetch filter definitions during application startup."""
    session = await get_session()
    try:
        names = await session.get_filter_labels()
    except Exception as exc:  # pragma: no cover - device dependent
        logger.warning(
            "filterwheel.preload_failed",
            error=str(exc),
            error_type=type(exc).__name__,
        )
        return

    if not names:
        logger.warning("filterwheel.preload_empty")
        return

    state.set_names(names)
    position = session.get_filter_position()
    if position is not None and 0 <= position < len(names):
        state.position = position
    logger.info("filterwheel.preload_ready", filters=names, position=state.position)


def _require_connected() -> None:
    if not state.connected:
        raise HTTPException(status_code=400, detail="Filter wheel not connected")


@router.get("/description")
def get_description():
    return alpaca_response(value="DWARF 3 Filter Wheel")


@router.get("/name")
def get_name():
    return alpaca_response(value="DWARF 3 Filter Wheel")


@router.get("/driverversion")
def get_driver_version():
    return alpaca_response(value="0.1.0")


@router.get("/driverinfo")
def get_driver_info():
    return alpaca_response(value="DWARF Alpaca Filter Wheel Driver")


@router.get("/interfaceversion")
def get_interface_version():
    return alpaca_response(value=2)


@router.get("/supportedactions")
def get_supported_actions():
    return alpaca_response(value=[])


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
        await session.acquire("filterwheel")
        try:
            names = await session.get_filter_labels()
            if not names:
                raise RuntimeError("no_filters")
            state.set_names(names)
            position = session.get_filter_position()
            if position is None or position < 0 or position >= len(names):
                try:
                    selected = await session.set_filter_position(0)
                    position = 0
                    logger.info(
                        "filterwheel.initialize_position",
                        filter=selected,
                        position=position,
                    )
                except RuntimeError as exc:
                    if str(exc) == "filter_control_unavailable":
                        raise HTTPException(
                            status_code=503,
                            detail="Filter wheel controls unavailable (device offline)",
                        ) from exc
                    raise
            state.position = position
            state.connected = True
            logger.info("filterwheel.connected", filters=names, position=position)
        except HTTPException:
            state.connected = False
            state.position = None
            await session.release("filterwheel")
            raise
        except Exception as exc:
            state.connected = False
            state.position = None
            await session.release("filterwheel")
            logger.warning(
                "filterwheel.connect_failed",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            raise HTTPException(status_code=500, detail="Failed to connect filter wheel") from exc
        return alpaca_response()

    if state.connected:
        await session.release("filterwheel")
    state.connected = False
    state.position = None
    logger.info("filterwheel.disconnected")
    return alpaca_response()


@router.get("/names")
async def get_names():
    if not state.names and state.connected:
        session = await get_session()
        try:
            state.set_names(await session.get_filter_labels())
        except Exception as exc:  # pragma: no cover - device dependent
            logger.warning(
                "filterwheel.names_refresh_failed",
                error=str(exc),
                error_type=type(exc).__name__,
            )
    return alpaca_response(value=state.names)


@router.get("/focusoffsets")
def get_focus_offsets():
    if len(state.focus_offsets) != len(state.names):
        state.focus_offsets = [0] * len(state.names)
    return alpaca_response(value=state.focus_offsets)


@router.get("/position")
async def get_position():
    _require_connected()
    session = await get_session()
    position = session.get_filter_position()
    if position is None:
        raise HTTPException(status_code=500, detail="Filter wheel position unknown")
    state.position = position
    return alpaca_response(value=position)


@router.put("/position")
async def put_position(
    request: Request,
    Position_query: int | None = Query(None, alias="Position"),
):
    _require_connected()
    position = await resolve_parameter(request, "Position", int, Position_query)
    if position < 0 or position >= len(state.names):
        raise HTTPException(status_code=400, detail="Position out of range")
    session = await get_session()
    try:
        selected = await session.set_filter_position(position)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Position out of range") from exc
    except Exception as exc:  # pragma: no cover - device dependent
        logger.warning(
            "filterwheel.move_failed",
            position=position,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        raise HTTPException(status_code=500, detail="Failed to move filter wheel") from exc
    state.position = position
    logger.info("filterwheel.position_set", position=position, filter=selected)
    return alpaca_response()
