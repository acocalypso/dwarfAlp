from __future__ import annotations

from fastapi import APIRouter, Depends

from ..devices.utils import alpaca_response, bind_request_context
from ..discovery import DEVICE_LIST

SERVER_DESCRIPTION = {
    "ServerName": "DWARF 3 Alpaca Server",
    "Manufacturer": "Astro Tools",
    "ManufacturerVersion": "0.1.0",
    "Location": "Observatory",
}

router = APIRouter(dependencies=[Depends(bind_request_context)])


@router.get("/health")
def healthcheck() -> dict[str, str]:
    """Basic health endpoint for monitoring and tests."""
    return {"status": "ok"}


@router.get("/apiversions")
def get_api_versions():
    return alpaca_response(value=[1])


@router.get("/v1/description")
def get_description():
    return alpaca_response(value=SERVER_DESCRIPTION)


@router.get("/v1/configureddevices")
def get_configured_devices():
    devices = [
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
    ]
    return alpaca_response(value=devices)


@router.get("/v1/devicelist")
def get_device_list():
    return alpaca_response(value=DEVICE_LIST)
