# Windows Control Center

The Control Center is the normal Windows entry point. It starts and stops the Alpaca
server, selects the device profile, provisions Wi-Fi, and displays runtime logs.

## Server tab

Use **Start server** only after confirming the values on **Settings**. The log panel
shows preflight, master-lock, calibration, capture, and shutdown events. Stop the
server from the same window before closing the application or changing models.

![Server tab](../../images/Setup/2.jpg)

## Settings tab

- **HTTP host/port:** where Alpaca listens. The defaults are `0.0.0.0:11111`.
- **DWARF IP/model/client ID:** must describe the same physical device.
- **Force simulation mode:** prevents hardware access.
- **Skip connectivity preflight:** intended for diagnosis, not ordinary startup.
- **Calibration after server start:** autofocuses at startup and prepares the first
  target-based calibration. It may cause movement after a NINA slew.
- **Coordinates/time zone:** used by calibration and mount reporting.

![Settings tab](../../images/Setup/3.1.jpg)

## Provisioning tab

The tab discovers DWARF units over BLE, requests nearby Wi-Fi networks, and sends
STA credentials. A successful operation updates the selected model and address used
by **Start server**.

![Provisioning tab](../../images/Setup/1.jpg)

Provisioning writes credentials to `var\connectivity.json`. Read
[sensitive runtime state](../user-guide/configuration.md#sensitive-runtime-state)
before sharing files from the application folder.
