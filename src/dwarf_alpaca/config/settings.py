from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the DWARF Alpaca server."""

    model_config = SettingsConfigDict(env_prefix="DWARF_ALPACA_", env_file=".env", extra="allow")

    http_host: str = "0.0.0.0"
    http_port: int = 11111
    http_scheme: str = "http"
    enable_https: bool = False
    tls_certfile: Optional[Path] = None
    tls_keyfile: Optional[Path] = None
    http_advertise_host: Optional[str] = None

    discovery_enabled: bool = True
    discovery_interface: str = "0.0.0.0"
    discovery_port: int = 32227

    state_directory: Path = Path("var")
    profiles_path: Optional[Path] = None

    timezone_name: Optional[str] = None
    site_latitude: Optional[float] = None
    site_longitude: Optional[float] = None
    geolocation_lookup_url: str = "https://ipwho.is/"

    dwarf_ap_ip: str = "192.168.88.1"
    dwarf_http_port: int = 8082
    dwarf_jpeg_port: int = 8092
    dwarf_ws_port: int = 9900
    dwarf_rtsp_port: int = 554
    dwarf_ftp_port: int = 21
    dwarf_device_model: str = "dwarf3"
    dwarf_ws_client_id: str = "0000DAF3-0000-1000-8000-00805F9B34FB"

    http_timeout_seconds: float = 5.0
    http_retries: int = 3
    stream_buffer_seconds: float = 1.5
    ftp_timeout_seconds: float = 10.0
    ftp_poll_interval_seconds: float = 1.0
    ws_ping_interval_seconds: float = 5.0
    temperature_refresh_interval_seconds: float = 5.0
    temperature_stale_after_seconds: float = 20.0
    goto_command_timeout_seconds: float = 45.0
    goto_completion_timeout_seconds: float = 120.0
    camera_gain_command_timeout_seconds: float = 2.0
    camera_disconnect_timeout_seconds: float = 5.0
    go_live_before_exposure: bool = True
    # Destructive and opt-in: after an astronomy FITS has been downloaded, delete
    # that capture's whole session (raw FITS, stacked FITS, previews) from the
    # DWARF album through POST /album/delete.
    delete_astro_session_after_download: bool = False
    delete_astro_session_timeout_seconds: float = 180.0
    # Opt-in: keep one DWARF astronomy session running for a whole NINA sequence
    # and hand each new raw FITS to the next StartExposure, instead of opening and
    # closing a DWARF session per frame (closing takes ~70 s in DSO mode).
    # DWARF 3 light frames always use a continuous session; False is only a
    # diagnostic fallback to the original one-session-per-frame path (CLI/env).
    continuous_astro_session: bool = True
    continuous_astro_max_frames: int = 999
    continuous_astro_idle_timeout_seconds: float = 120.0
    # How long a new capture waits for the DWARF to finish closing the previous
    # session (DWARF 3 DSO mode needs about 70 s).
    astro_capture_ready_timeout_seconds: float = 150.0
    go_live_timeout_seconds: float = 5.0
    # Capture strategy for DWARF mini: "astro" (FITS/live-stacking flow) or "photo" (single JPG flow).
    dwarf_mini_capture_mode: str = "astro"
    # Direct PHOTO_RAW/PHOTOGRAPH does not currently prove long-exposure/gain/raw output.
    allow_unverified_direct_photo: bool = False
    capture_start_evidence_timeout_seconds: float = 3.0
    # The official app offers "Continue" when a matching dark is missing or
    # outside its temperature tolerance. Alpaca clients such as NINA cannot
    # answer that interactive prompt, so continue by default and log it.
    allow_continue_without_darks: bool = True
    dark_check_timeout_seconds: float = 5.0
    goto_valid_seconds: float = 300.0
    calibration_valid_seconds: float = 900.0
    # Astro autofocus before the DWARF calibrates (GOTO or calibration after
    # start). Off by default: DWARF 3 firmware V1.5.4.1 acknowledges the command
    # but never starts autofocus, which cost 20 s on every GOTO.
    autofocus_before_calibration: bool = False
    calibration_autofocus_timeout_seconds: float = 120.0
    calibration_autofocus_start_timeout_seconds: float = 20.0
    calibration_timeout_seconds: float = 300.0
    calibration_wait_for_slew_seconds: float = 420.0
    auto_calibrate_on_slew: bool = True
    # Use the one-click GOTO (11013) for every slew, also after a calibration.
    # Sky test 2026-11-19 (DWARF 3 firmware V1.5.4.1, EQ mode): after dwarfAlp
    # calibrated, the plain GOTO (11002) was accepted but the DWARF never moved.
    # The one-click GOTO skips calibration when the DWARF is already calibrated.
    always_one_click_goto: bool = True
    # Turn the DWARF's lights off when dwarfAlp connects (they stay off; the
    # DWARFLAB app can turn them on again). 13501 ring light, 13504 battery
    # indicator.
    ring_light_off: bool = False
    battery_indicator_off: bool = False
    calibrate_after_server_start: bool = False
    focuser_target_tolerance_steps: int = 5

    ble_adapter: Optional[str] = None
    ble_password: Optional[str] = None
    ble_response_timeout_seconds: float = 15.0
    provisioning_timeout_seconds: float = 120.0

    force_simulation: bool = False
    network_mode: str = "ap"

    def with_timezone_name(self, tz_name: Optional[str]) -> "Settings":
        data = self.model_dump()
        data["timezone_name"] = tz_name
        return type(self).model_validate(data)


def normalize_dwarf_device_model(value: Optional[str]) -> str:
    """Normalize user-facing DWARF model labels to internal profile ids."""

    normalized = (value or "").strip().lower().replace("_", " ").replace("-", " ")
    collapsed = " ".join(part for part in normalized.split() if part)

    if collapsed in {"dwarf mini", "mini", "dwarfmini", "dwarf4", "dwarf 4"}:
        return "dwarfmini"
    if collapsed in {"dwarf 2", "dwarf2"}:
        return "dwarf2"
    if collapsed in {"dwarf 3", "dwarf3"}:
        return "dwarf3"

    return "dwarf3"


def load_settings(config_path: Optional[str]) -> Settings:
    """Load settings optionally layering a YAML profile file."""
    settings = Settings()
    if config_path:
        from .yaml_loader import load_yaml_settings

        return load_yaml_settings(settings, config_path)
    return settings
