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

    dwarf_ap_ip: str = "192.168.88.1"
    dwarf_http_port: int = 8082
    dwarf_jpeg_port: int = 8092
    dwarf_ws_port: int = 9900
    dwarf_rtsp_port: int = 554
    dwarf_ftp_port: int = 21
    dwarf_ws_client_id: str = "0000DAF3-0000-1000-8000-00805F9B34FB"

    http_timeout_seconds: float = 5.0
    http_retries: int = 3
    stream_buffer_seconds: float = 1.5
    ftp_timeout_seconds: float = 10.0
    ftp_poll_interval_seconds: float = 1.0
    ws_ping_interval_seconds: float = 5.0
    temperature_refresh_interval_seconds: float = 5.0
    temperature_stale_after_seconds: float = 20.0
    camera_gain_command_timeout_seconds: float = 2.0
    go_live_before_exposure: bool = True
    go_live_timeout_seconds: float = 5.0
    allow_continue_without_darks: bool = True
    dark_check_timeout_seconds: float = 5.0
    goto_valid_seconds: float = 300.0
    calibration_valid_seconds: float = 900.0
    calibration_timeout_seconds: float = 60.0
    calibration_wait_for_slew_seconds: float = 10.0
    focuser_target_tolerance_steps: int = 5

    ble_adapter: Optional[str] = None
    ble_password: Optional[str] = None
    ble_response_timeout_seconds: float = 15.0
    provisioning_timeout_seconds: float = 120.0

    force_simulation: bool = False
    network_mode: str = "ap"


def load_settings(config_path: Optional[str]) -> Settings:
    """Load settings optionally layering a YAML profile file."""
    settings = Settings()
    if config_path:
        from .yaml_loader import load_yaml_settings

        return load_yaml_settings(settings, config_path)
    return settings
