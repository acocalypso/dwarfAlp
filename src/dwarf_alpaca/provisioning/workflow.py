from __future__ import annotations

from pathlib import Path

import structlog

from ..config.settings import Settings
from ..dwarf.ble_provisioner import DwarfBleProvisioner
from ..dwarf.state import StateStore


logger = structlog.get_logger(__name__)


async def provision_sta(
    *,
    settings: Settings,
    ssid: str,
    password: str,
    adapter: str | None,
    ble_password: str | None,
    device_address: str | None = None,
) -> None:
    """Provision DWARF onto the local WLAN using BLE."""

    state_store = create_state_store(settings.state_directory)

    if not ssid:
        raise RuntimeError("Wi-Fi SSID is required for provisioning")

    if password is None or password == "":
        state_store.record_error("Wi-Fi password missing for provisioning")
        raise RuntimeError("Wi-Fi password is required for provisioning")

    provisioner = DwarfBleProvisioner(
        response_timeout=settings.ble_response_timeout_seconds
    )

    resolved_adapter = adapter or settings.ble_adapter
    resolved_password = ble_password or settings.ble_password

    if resolved_password is None:
        raise RuntimeError(
            "BLE password is required; set --ble-password or DWARF_ALPACA_BLE_PASSWORD"
        )

    logger.info("provision.workflow.start", ssid=ssid, adapter=resolved_adapter)
    result = await provisioner.provision(
        ssid=ssid,
        password=password,
        adapter=resolved_adapter,
        ble_password=resolved_password,
        timeout=settings.provisioning_timeout_seconds,
        device=device_address,
    )

    if result.success and result.sta_ip:
        state = state_store.load()
        state.sta_ip = result.sta_ip
        state.mode = "sta"
        state.last_error = None
        state.wifi_credentials[ssid] = password
        state_store.save(state)
        logger.info("provision.workflow.success", sta_ip=result.sta_ip)
        return

    message = result.message if not result.success else "Unknown provisioning error"
    logger.error("provision.workflow.failure", message=message)
    state_store.record_error(message)
    raise RuntimeError(message)


def create_state_store(state_dir: Path) -> StateStore:
    path = state_dir / "connectivity.json"
    return StateStore(path=path)
