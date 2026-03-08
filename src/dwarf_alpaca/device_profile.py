from __future__ import annotations

from dataclasses import dataclass

from .config.settings import Settings, normalize_dwarf_device_model


@dataclass(frozen=True)
class CameraProfile:
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
    electrons_per_adu: tuple[float, ...]
    full_well_capacity_e: tuple[float, ...]
    raw_format: str
    bayer_pattern: str


@dataclass(frozen=True)
class DeviceProfile:
    model_id: str
    display_name: str
    ws_client_id: str
    has_filterwheel: bool
    camera: CameraProfile


_DWARF3 = DeviceProfile(
    model_id="dwarf3",
    display_name="DWARF 3",
    ws_client_id="0000DAF3-0000-1000-8000-00805F9B34FB",
    has_filterwheel=True,
    camera=CameraProfile(
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
        electrons_per_adu=(2.75,),
        full_well_capacity_e=(11270.0,),
        raw_format="SRGGB12",
        bayer_pattern="RGGB",
    ),
)

_DWARFMINI = DeviceProfile(
    model_id="dwarfmini",
    display_name="DWARF mini",
    ws_client_id="0000DAF4-0000-1000-8000-00805F9B34FB",
    has_filterwheel=False,
    camera=CameraProfile(
        name="Sony IMX662",
        # IMX662 active pixels are commonly reported as 1920x1080.
        resolution_x=1920,
        resolution_y=1080,
        bits_per_pixel=16,
        ad_converter_bits=12,
        max_binning=2,
        pixel_size_um=2.9,
        max_gain_db=200.0,
        min_exposure_s=0.00001,
        max_exposure_s=120.0,
        electrons_per_adu=(2.75,),
        full_well_capacity_e=(11270.0,),
        raw_format="SRGGB12",
        bayer_pattern="RGGB",
    ),
)

_DWARF2 = DeviceProfile(
    model_id="dwarf2",
    display_name="DWARF 2",
    ws_client_id="0000DAF2-0000-1000-8000-00805F9B34FB",
    has_filterwheel=False,
    camera=CameraProfile(
        name="Sony IMX415",
        resolution_x=3840,
        resolution_y=2160,
        bits_per_pixel=16,
        ad_converter_bits=12,
        max_binning=2,
        pixel_size_um=1.45,
        max_gain_db=200.0,
        min_exposure_s=0.00001,
        max_exposure_s=120.0,
        electrons_per_adu=(2.75,),
        full_well_capacity_e=(11270.0,),
        raw_format="SRGGB12",
        bayer_pattern="RGGB",
    ),
)

_PROFILES: dict[str, DeviceProfile] = {
    "dwarf3": _DWARF3,
    "dwarfmini": _DWARFMINI,
    "dwarf2": _DWARF2,
}

_active_model_id = "dwarf3"


def configure_device_profile(settings: Settings) -> None:
    global _active_model_id
    _active_model_id = normalize_dwarf_device_model(settings.dwarf_device_model)


def get_active_device_profile() -> DeviceProfile:
    return _PROFILES.get(_active_model_id, _DWARF3)


def get_device_profile(model: str | None) -> DeviceProfile:
    model_id = normalize_dwarf_device_model(model)
    return _PROFILES.get(model_id, _DWARF3)


def build_device_list(profile: DeviceProfile) -> list[dict[str, object]]:
    server_prefix = profile.display_name.replace(" ", "")
    devices: list[dict[str, object]] = [
        {
            "DeviceName": f"{profile.display_name} Telescope",
            "DeviceType": "Telescope",
            "DeviceNumber": 0,
            "UniqueID": f"{server_prefix}-Telescope",
        },
        {
            "DeviceName": f"{profile.display_name} Camera",
            "DeviceType": "Camera",
            "DeviceNumber": 0,
            "UniqueID": f"{server_prefix}-Camera",
        },
        {
            "DeviceName": f"{profile.display_name} Focuser",
            "DeviceType": "Focuser",
            "DeviceNumber": 0,
            "UniqueID": f"{server_prefix}-Focuser",
        },
    ]
    if profile.has_filterwheel:
        devices.append(
            {
                "DeviceName": f"{profile.display_name} Filter Wheel",
                "DeviceType": "FilterWheel",
                "DeviceNumber": 0,
                "UniqueID": f"{server_prefix}-FilterWheel",
            }
        )
    return devices
