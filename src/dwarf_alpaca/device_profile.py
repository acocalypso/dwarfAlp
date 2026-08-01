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
    min_gain_db: float
    max_gain_db: float
    min_exposure_s: float
    max_exposure_s: float
    electrons_per_adu: tuple[float, ...]
    full_well_capacity_e: tuple[float, ...]
    raw_format: str
    bayer_pattern: str


@dataclass(frozen=True)
class ProtocolProfile:
    """Wire-level defaults observed for a device protocol family."""

    family: str
    ws_major_version: int
    ws_minor_version: int
    ws_device_id: int
    camera_commands: str
    focus_commands: str
    supports_runtime_discovery: bool


@dataclass(frozen=True)
class CaptureCapabilities:
    """Capture behavior the driver can honestly implement for a profile."""

    default_workflow: str
    supports_astro_workflow: bool
    supports_direct_photo: bool
    supports_fits: bool
    supports_binning: bool
    supports_frame_count: bool
    supports_progress_notifications: bool
    supports_observation_notifications: bool
    supports_stop: bool
    supports_abort: bool


@dataclass(frozen=True)
class FilterCapabilities:
    labels: tuple[str, ...]
    firmware_indices: tuple[int, ...]
    control_path: str
    runtime_discovery: bool


@dataclass(frozen=True)
class DeviceProfile:
    model_id: str
    display_name: str
    ws_client_id: str
    has_filterwheel: bool
    camera: CameraProfile
    protocol: ProtocolProfile
    capture: CaptureCapabilities
    filters: FilterCapabilities


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
        min_gain_db=0.0,
        max_gain_db=200.0,
        min_exposure_s=0.00001,
        max_exposure_s=120.0,
        electrons_per_adu=(2.75,),
        full_well_capacity_e=(11270.0,),
        raw_format="SRGGB12",
        bayer_pattern="RGGB",
    ),
    protocol=ProtocolProfile(
        family="v3",
        ws_major_version=1,
        ws_minor_version=20,
        ws_device_id=4,
        camera_commands="v3",
        focus_commands="v3",
        supports_runtime_discovery=True,
    ),
    capture=CaptureCapabilities(
        default_workflow="astro",
        supports_astro_workflow=True,
        supports_direct_photo=True,
        supports_fits=True,
        supports_binning=True,
        supports_frame_count=True,
        supports_progress_notifications=True,
        supports_observation_notifications=True,
        supports_stop=False,
        supports_abort=True,
    ),
    filters=FilterCapabilities(
        labels=("VIS Filter", "Astro Filter", "Duo-Band Filter"),
        firmware_indices=(0, 1, 2),
        control_path="v3-camera-param",
        runtime_discovery=False,
    ),
)

_DWARFMINI = DeviceProfile(
    model_id="dwarfmini",
    display_name="DWARF mini",
    ws_client_id="0000DAF4-0000-1000-8000-00805F9B34FB",
    has_filterwheel=True,
    camera=CameraProfile(
        name="Sony IMX662",
        # IMX662 active pixels are commonly reported as 1920x1080.
        resolution_x=1920,
        resolution_y=1080,
        bits_per_pixel=16,
        ad_converter_bits=12,
        max_binning=1,
        pixel_size_um=2.9,
        min_gain_db=40.0,
        max_gain_db=100.0,
        min_exposure_s=1.0,
        max_exposure_s=180.0,
        electrons_per_adu=(2.75,),
        full_well_capacity_e=(11270.0,),
        raw_format="SRGGB12",
        bayer_pattern="RGGB",
    ),
    protocol=ProtocolProfile(
        family="v3",
        ws_major_version=1,
        ws_minor_version=20,
        ws_device_id=4,
        camera_commands="v3",
        focus_commands="v3",
        supports_runtime_discovery=True,
    ),
    capture=CaptureCapabilities(
        default_workflow="astro",
        supports_astro_workflow=True,
        supports_direct_photo=True,
        supports_fits=True,
        supports_binning=True,
        supports_frame_count=True,
        supports_progress_notifications=True,
        supports_observation_notifications=True,
        supports_stop=False,
        supports_abort=True,
    ),
    filters=FilterCapabilities(
        labels=("Astro", "Duo-Band"),
        firmware_indices=(1, 2),
        control_path="astro-start-ir-index",
        runtime_discovery=False,
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
        min_gain_db=0.0,
        max_gain_db=200.0,
        min_exposure_s=0.00001,
        max_exposure_s=120.0,
        electrons_per_adu=(2.75,),
        full_well_capacity_e=(11270.0,),
        raw_format="SRGGB12",
        bayer_pattern="RGGB",
    ),
    protocol=ProtocolProfile(
        family="v3",
        ws_major_version=1,
        ws_minor_version=20,
        ws_device_id=4,
        camera_commands="v3",
        focus_commands="v3",
        supports_runtime_discovery=True,
    ),
    capture=CaptureCapabilities(
        default_workflow="astro",
        supports_astro_workflow=True,
        supports_direct_photo=True,
        supports_fits=True,
        supports_binning=True,
        supports_frame_count=True,
        supports_progress_notifications=True,
        supports_observation_notifications=True,
        supports_stop=False,
        supports_abort=True,
    ),
    filters=FilterCapabilities(
        labels=(),
        firmware_indices=(),
        control_path="none",
        runtime_discovery=False,
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
