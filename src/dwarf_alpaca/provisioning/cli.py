from __future__ import annotations

import asyncio
from getpass import getpass
from typing import Sequence

from .workflow import create_state_store, provision_sta
from ..config.settings import Settings
from ..dwarf.ble_provisioner import DwarfBleProvisioner, ProvisioningError
from ..dwarf.ble_packets import DEFAULT_BLE_PASSWORD


async def _prompt(message: str, *, default: str | None = None, secret: bool = False) -> str:
    prompt_text = message
    if default is not None:
        prompt_text = f"{message} [{default}]: "
    else:
        prompt_text = f"{message}: "

    def _ask() -> str:
        if secret:
            return getpass(prompt_text)
        return input(prompt_text)

    result = await asyncio.to_thread(_ask)
    return result or (default or "")


async def provision_command(
    *,
    settings: Settings,
    ssid: str,
    password: str,
    adapter: str | None,
    ble_password: str | None,
    device_address: str | None = None,
) -> None:
    """CLI helper to provision DWARF onto STA Wi-Fi."""
    await provision_sta(
        settings=settings,
        ssid=ssid,
        password=password,
        adapter=adapter,
        ble_password=ble_password,
        device_address=device_address,
    )


async def provision_guide_command(
    *,
    settings: Settings,
    adapter: str | None,
    ble_password: str | None,
) -> None:
    print("🔍 Scanning for DWARF devices over BLE…")

    resolved_adapter = adapter or settings.ble_adapter
    state_store = create_state_store(settings.state_directory)
    state = state_store.load()
    provisioner = DwarfBleProvisioner(
        response_timeout=settings.ble_response_timeout_seconds
    )

    devices = await DwarfBleProvisioner.discover_devices(adapter=resolved_adapter)
    if not devices:
        print("No DWARF devices found. Ensure the unit is powered on and BLE is enabled.")
        return

    for idx, device in enumerate(devices, start=1):
        print(f"  [{idx}] {device.name} ({device.address})")

    selection_raw = await _prompt("Select device", default="1")
    try:
        selection_index = max(1, min(len(devices), int(selection_raw)))
    except ValueError:
        selection_index = 1

    chosen = devices[selection_index - 1]
    print(f"➡️  Using {chosen.name} ({chosen.address})")

    resolved_ble_password = ble_password or settings.ble_password
    if not resolved_ble_password:
        resolved_ble_password = await _prompt(
            "Enter BLE password",
            default=DEFAULT_BLE_PASSWORD,
            secret=False,
        )
    elif resolved_ble_password == "-":
        resolved_ble_password = await _prompt(
            "Enter BLE password",
            default=DEFAULT_BLE_PASSWORD,
            secret=False,
        )

    ssid_options: Sequence[str] = []
    print("📡 Requesting Wi-Fi networks (this may take a few seconds)…")
    try:
        wifi_list = await provisioner.fetch_wifi_list(
            device=chosen,
            adapter=resolved_adapter,
            ble_password=resolved_ble_password,
            timeout=settings.provisioning_timeout_seconds,
        )
        ssid_options = sorted({ssid for ssid in wifi_list if ssid})
    except ProvisioningError as exc:
        print(f"⚠️  Could not retrieve Wi-Fi list: {exc}")
    except Exception as exc:  # pragma: no cover - hardware specific
        print(f"⚠️  Unexpected error while reading Wi-Fi list: {exc}")

    saved_password: str | None = None

    if ssid_options:
        for idx, ssid in enumerate(ssid_options, start=1):
            print(f"  [{idx}] {ssid}")
        print("  [0] Enter SSID manually")
        ssid_choice_raw = await _prompt("Select Wi-Fi network", default="1")
        try:
            ssid_choice = int(ssid_choice_raw)
        except ValueError:
            ssid_choice = 1

        if ssid_choice <= 0 or ssid_choice > len(ssid_options):
            ssid = await _prompt("Enter Wi-Fi SSID")
        else:
            ssid = ssid_options[ssid_choice - 1]
    else:
        ssid = await _prompt("Enter Wi-Fi SSID")

    saved_password = state.wifi_credentials.get(ssid)
    wifi_password: str | None = None
    while True:
        if saved_password:
            print(
                f"🔐 Found saved password for '{ssid}'. Press Enter to reuse it or type a new password."
            )
            entered = await _prompt("Enter Wi-Fi password", secret=True)
            wifi_password = entered or saved_password
        else:
            wifi_password = await _prompt("Enter Wi-Fi password", secret=True)

        if wifi_password:
            break

        print(
            "⚠️  Wi-Fi password cannot be empty. Please enter a password or press Ctrl+C to cancel."
        )

    print("🚀 Starting provisioning…")
    await provision_sta(
        settings=settings,
        ssid=ssid,
        password=wifi_password,
        adapter=resolved_adapter,
        ble_password=resolved_ble_password,
        device_address=chosen.address,
    )
    print("✅ Provisioning completed. Check var/connectivity.json for the reported STA IP.")
