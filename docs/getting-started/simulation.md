# Simulation mode

Simulation runs the same Alpaca HTTP and discovery surfaces without opening a DWARF
WebSocket, HTTP, FTP, RTSP, or BLE connection. Use it to test installation, firewall
rules, NINA discovery, and client configuration.

## Control Center

1. Enable **Force simulation mode** in **Settings**.
2. Select a model. The advertised device set follows that profile; DWARF 2 has no
   filter wheel.
3. Start the server and connect NINA.

## Command line

```powershell
$env:DWARF_ALPACA_FORCE_SIMULATION = "true"
$env:DWARF_ALPACA_DISCOVERY_ENABLED = "false"
uv run dwarf-alpaca serve
```

Open <http://127.0.0.1:11111/management/apiversions> to verify startup. Press
`Ctrl+C` to stop it. Discovery is disabled in this example so it is safe to run on a
development machine; enable it when testing NINA's network scan.

Simulation proves the client/server integration only. It does not certify physical
protocol behavior, FITS transfer, filters, focusing, calibration, or movement.
