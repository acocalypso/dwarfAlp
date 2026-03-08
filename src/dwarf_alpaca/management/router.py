from __future__ import annotations

from fastapi import APIRouter, Depends

from ..devices.utils import alpaca_response, bind_request_context
from ..device_profile import build_device_list, get_active_device_profile


def _server_description() -> dict[str, str]:
    profile = get_active_device_profile()
    return {
        "ServerName": f"{profile.display_name} Alpaca Server",
        "Manufacturer": "Astro Tools",
        "ManufacturerVersion": "0.1.0",
        "Location": "Observatory",
    }


def _device_list() -> list[dict[str, object]]:
    return build_device_list(get_active_device_profile())

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
    return alpaca_response(value=_server_description())


@router.get("/v1/configureddevices")
def get_configured_devices():
    devices = [dict(device) for device in _device_list()]
    return alpaca_response(value=devices)


@router.get("/v1/devicelist")
def get_device_list():
    return alpaca_response(value=_device_list())
