from __future__ import annotations

from dataclasses import dataclass

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ..dwarf.session import get_session
from .utils import alpaca_response, bind_request_context, resolve_parameter
router = APIRouter(dependencies=[Depends(bind_request_context)])


@dataclass
class FocuserState:
    connected: bool = False
    position: int = 0
    is_moving: bool = False
    step_size: int = 50
    max_step: int = 20000
    max_increment: int = 20000
    is_inverted: bool = False


state = FocuserState()


@router.get("/description")
def get_description():
    return alpaca_response(value="DWARF 3 Focuser")


@router.get("/name")
def get_name():
    return alpaca_response(value="DWARF 3 Focuser")


@router.get("/driverversion")
def get_driver_version():
    return alpaca_response(value="0.1.0")


@router.get("/interfaceversion")
def get_interface_version():
    return alpaca_response(value=3)


@router.get("/absolute")
def get_absolute():
    return alpaca_response(value=True)


@router.get("/maxstep")
def get_max_step():
    return alpaca_response(value=state.max_step)


@router.get("/maxincrement")
def get_max_increment():
    return alpaca_response(value=state.max_increment)


@router.get("/isinverted")
def get_is_inverted():
    return alpaca_response(value=state.is_inverted)


@router.put("/isinverted")
def set_is_inverted(Inverted: bool = Query(..., alias="Inverted")):
    if Inverted:
        raise HTTPException(status_code=400, detail="Inverted operation not supported")
    state.is_inverted = False
    return alpaca_response()


@router.get("/temperature")
def get_temperature():
    return alpaca_response(value=20.0)


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
        await session.acquire("focuser")
        await session.focuser_connect()
    else:
        await session.focuser_disconnect()
        await session.release("focuser")
    runtime = session.focuser_state
    state.position = runtime.position
    state.is_moving = runtime.is_moving
    state.connected = runtime.connected
    return alpaca_response()


@router.get("/ismoving")
def get_is_moving():
    return alpaca_response(value=state.is_moving)


@router.get("/position")
def get_position():
    return alpaca_response(value=state.position)


@router.put("/move")
async def move(Position: int = Query(...)):
    if not state.connected:
        raise HTTPException(status_code=400, detail="Focuser not connected")
    if Position < 0 or Position > state.max_step:
        raise HTTPException(status_code=400, detail="Position out of range")

    session = await get_session()
    runtime = session.focuser_state
    current_position = runtime.position
    delta = Position - current_position
    if delta == 0:
        return alpaca_response()

    state.is_moving = True
    await session.focuser_move(delta)
    runtime = session.focuser_state
    state.position = runtime.position
    state.is_moving = runtime.is_moving
    state.connected = runtime.connected
    return alpaca_response()


@router.put("/halt")
async def halt():
    session = await get_session()
    await session.focuser_halt()
    runtime = session.focuser_state
    state.is_moving = runtime.is_moving
    state.position = runtime.position
    state.connected = runtime.connected
    return alpaca_response()


@router.get("/stepsize")
def get_step_size():
    return alpaca_response(value=state.step_size)


@router.get("/tempcomp")
def get_temp_comp():
    return alpaca_response(value=False)


@router.get("/tempcompavailable")
def get_temp_comp_available():
    return alpaca_response(value=False)


@router.put("/tempcomp")
def set_temp_comp(TempComp: bool = Query(..., alias="TempComp")):
    if TempComp:
        raise HTTPException(status_code=400, detail="Temperature compensation not supported")
    return alpaca_response()

