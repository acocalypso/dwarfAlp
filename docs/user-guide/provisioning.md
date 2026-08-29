# Wi-Fi and BLE provisioning

Provisioning places the DWARF in station (STA) mode on the same network as the PC.
It is optional when you use the telescope's own access point (AP mode).

## Control Center workflow

1. Turn on Bluetooth and Wi-Fi on the PC, then power on the DWARF nearby.
2. Open **Provisioning** and select **Discover devices**.
3. Select the exact discovered unit. This updates the model selection.
4. Select **Fetch Wi-Fi list**, choose the intended SSID, and enter its password.
5. Enter the device BLE password. Do not put a real password in screenshots or logs.
6. Select **Provision Wi-Fi** and wait for a successful STA address.
7. Return to **Settings** and verify that the discovered model and STA IP—not the
   former defaults—are selected before starting the server.

![Provisioning workflow](../../images/Setup/1.jpg)

The DWARF and PC must be able to reach each other on the selected network. Guest Wi-Fi
or client isolation can block local device traffic and Alpaca discovery.

## Command line

Use the interactive guide when running from source:

```powershell
uv run dwarf-alpaca guide --ble-password "<device-ble-password>"
```

For non-interactive provisioning, inspect the current options first:

```powershell
uv run dwarf-alpaca provision --help
```

Provisioning state is stored in `var/connectivity.json`, including saved Wi-Fi
credentials. Protect and redact that file as described in
[configuration](configuration.md#sensitive-runtime-state).
