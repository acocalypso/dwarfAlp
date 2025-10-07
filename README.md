# DWARF 3 Alpaca Server

An ASCOM Alpaca device hub for the DWARF 3 smart telescope. The project speaks the DWARF control protocols (websocket, HTTP/JSON, FTP, RTSP, BLE) and exposes Telescope/0, Camera/0, Focuser/0, and FilterWheel/0 devices that can be driven from clients such as NINA, Voyager, or ASCOM Remote.

---

## Highlights

- **End-to-end DWARF bridge** – `DwarfSession` maintains websocket, HTTP, FTP, and BLE clients, negotiates the master lock, and caches notifications for low-latency Alpaca responses.
- **Full Alpaca surface area** – Telescope, camera, focuser, and filter wheel routers translate Alpaca verbs into real DWARF commands including go-to slews, joystick motion, exposure setup, filter selection, and temperature polling.
- **Capture pipeline** – Exposure requests map durations to DWARF parameter tables, monitor dark-library status, trigger astro captures, and harvest results from the onboard FTP album.
- **Filter handling** – Automatic discovery of filter definitions, IR-cut coordination, and persistence of the active slot for imaging tasks.
- **Provisioning workflow** – BLE onboarding stores STA credentials in `var/connectivity.json`, updates settings dynamically, and feeds the combined `dwarf-alpaca start` command.
- **Structured logging & tests** – `structlog` JSON output, rotating startup logs, and a pytest suite covering discovery, CLI flows, session orchestration, and device endpoints.

---

## Project Layout

```
├── docs/
│   ├── architecture.md       # Deep dive into services and data flow
│   ├── integration_plan.md   # Future integration checkpoints
│   └── DWARF API2.txt        # Vendor protocol notes
├── src/dwarf_alpaca/
│   ├── cli.py                # CLI entry point (serve/start/provision/guide)
│   ├── server.py             # FastAPI app, discovery service, filter preload
│   ├── config/               # Pydantic settings + YAML loader
│   ├── devices/              # Alpaca routers (telescope, camera, focuser, filter wheel)
│   ├── discovery.py          # UDP discovery responder
│   ├── dwarf/                # Session coordinator, ws/http/rtsp/ftp/BLE helpers
│   ├── management/           # Alpaca management endpoints
│   └── proto/                # Protobuf definitions generated from DWARF specs
├── tests/                    # pytest-based coverage of routers and helpers
├── var/                      # Runtime state (connectivity, logs, temp files)
├── scripts/                  # Maintenance helpers (config dumps, etc.)
├── pyproject.toml            # Packaging metadata and dependencies
└── README.md
```

---

## Quick Start

### 1. Prerequisites

- Python 3.10+
- Windows PowerShell (repo commands assume Windows; adjust paths for macOS/Linux)
- System packages required by `aiortc` / `av` (FFmpeg, libopus, etc.)
- Optional: Bluetooth adapter compatible with [Bleak](https://github.com/hbldh/bleak)

### 2. Create a virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
```

For development extras (ruff, pytest, httpx CLI):

```powershell
pip install -e .[development]
```

### 3. Choose a connection mode

| Scenario | How to run |
| --- | --- |
| **Simulation** | `setx DWARF_ALPACA_FORCE_SIMULATION true` (or use PowerShell `$env:DWARF_ALPACA_FORCE_SIMULATION = "true"` in-session) then `dwarf-alpaca serve`. The routers respond with synthetic data, ideal for UI development and tests. |
| **Hardware (existing Wi-Fi)** | Ensure the DWARF is connected to your Wi-Fi and that its STA IP is recorded in `var/connectivity.json` (or supply `--ssid`/`--password`). Run `dwarf-alpaca start --skip-provision --wait-timeout 180`. |
| **Hardware (provisioning required)** | Use the BLE guide to onboard Wi-Fi credentials: `dwarf-alpaca guide --adapter <optional-device> --ble-password <password>`. Credentials and STA IP are saved for subsequent runs. |

### 4. All-in-one launch

```powershell
dwarf-alpaca start --ssid "MySSID" --password "MyPassword" 
# ssid and password are optional arguments
```

- Prompts for BLE password if not provided (defaults to `DWARF_12345678`).
- Provisions the telescope, waits for STA connectivity, acquires the master lock, and starts the HTTP + discovery services.
- STA IP detection automatically updates `Settings.dwarf_ap_ip` before the server boots.

### 5. Point your Alpaca client

Configure clients like NINA to connect to `http://<server-ip>:11111`. Discovery responses advertise Telescope/0, Camera/0, Focuser/0, and FilterWheel/0.

---

## CLI Reference

| Command | Description |
| --- | --- |
| `dwarf-alpaca serve [--config path] [--ws-client-id value]` | Start only the Alpaca/HTTP/UDP services using the current settings. |
| `dwarf-alpaca start [options]` | Provision (optional), wait for connectivity, warm up the DWARF session, and then serve Alpaca. Supports `--skip-provision`, `--wait-timeout`, `--wait-interval`, and websocket client overrides. |
| `dwarf-alpaca guide [--adapter name] [--ble-password value]` | Interactive Bluetooth guide that lists DWARF devices, nearby SSIDs, and saves credentials. |
| `dwarf-alpaca provision [options] <SSID> <password>` | Non-interactive provisioning suitable for automation once you know the BLE address and Wi-Fi credentials. |

Rotating startup logs live in `var/logs/dwarf-alpaca-start.log` for later diagnosis.

---

## Configuration Cheatsheet

Settings may be supplied via env vars (`DWARF_ALPACA_*`), `.env`, or a YAML profile loaded with `--config`. Key options from `config/settings.py`:

| Setting | Default | Notes |
| --- | --- | --- |
| `http_host` / `http_port` | `0.0.0.0` / `11111` | Bind address and port for Alpaca HTTP API. |
| `http_scheme` | `http` | Switch to `https` when TLS files are provided. |
| `http_advertise_host` | `None` | Override the host reported in discovery packets. Auto-detected when unset. |
| `discovery_enabled` | `True` | Disable if another service handles UDP discovery. |
| `dwarf_ap_ip` | `192.168.88.1` | Fallback AP address. Overridden with STA IP after provisioning. |
| `dwarf_http_port` / `dwarf_jpeg_port` | `8082` / `8092` | DWARF REST/album ports. |
| `dwarf_ws_port` / `dwarf_rtsp_port` / `dwarf_ftp_port` | `9900` / `554` / `21` | Control-plane websocket, RTSP streaming, and FTP album ports. |
| `dwarf_ws_client_id` | `0000DAF3-0000-1000-8000-00805F9B34FB` | Client identifier required to acquire the master lock. Adjust per hardware variant. |
| `ws_ping_interval_seconds` | `5.0` | Heartbeat cadence for the websocket. |
| `go_live_before_exposure` | `True` | Enable/disable RTSP warm-up before astro captures. |
| `allow_continue_without_darks` | `True` | Permit exposures when the dark library check fails. |
| `temperature_refresh_interval_seconds` | `5.0` | How often to poll DWARF temperature notifications. |
| `ble_adapter` / `ble_password` | `None` | Defaults for provisioning workflows. |
| `force_simulation` | `False` | Bypass hardware access and return simulated data. |

See `config/profiles.yaml` for sample overlays.

---

## Runtime Architecture (Summary)

- **DiscoveryService** – Async UDP responder advertising device metadata and the HTTP URL.
- **FastAPI app** – Mounts Alpaca management, telescope, camera, focuser, and filter wheel routers. Middleware emits structured access logs.
- **DwarfSession** – Central orchestrator that:
  - Manages the websocket client (`DwarfWsClient`) for commands/notifications and master lock stewardship.
  - Wraps `DwarfHttpClient`, `DwarfFtpClient`, and `DwarfRtspClient` for REST, album, and live view access.
  - Handles exposure scheduling, filter presets, gain/exposure lookup tables, dark-library enforcement, and temperature monitoring.
  - Tracks device reference counts so connections tear down only when all Alpaca devices disconnect.
- **Provisioning workflow** – Uses `DwarfBleProvisioner` to push Wi-Fi credentials and persists STA state via `StateStore`.
- **Tests** – Cover CLI plumbing, UDP discovery packets, session behaviour, and endpoint compliance.

For a deeper exploration see [`docs/architecture.md`](docs/architecture.md).

---

## Observing Workflow

1. **Provision / connect** – Use `dwarf-alpaca start` to provision (if necessary) and acquire the DWARF master lock.
2. **Discover** – Clients broadcast Alpaca discovery; this server replies with Telescope/0, Camera/0, Focuser/0, FilterWheel/0 entries.
3. **Slew & track** – Telescope slews translate to DWARF astro GOTO commands; recent slews are cached for exposure validation.
4. **Focus** – Manual and continuous focus moves map to DWARF focus commands with live position updates from notifications.
5. **Filter selection** – Filter wheel positions are read from DWARF parameters; IR-cut toggles are applied when required.
6. **Capture** – Exposure requests ensure gain/exposure indices, start astro capture, watch dark library state, and fetch the resulting image via FTP.
7. **Telemetry** – Temperature and camera metadata stream back into Alpaca GET endpoints for real-time monitoring.

---

## Testing

```powershell
pytest
```

The suite includes UDP discovery tests, CLI smoke coverage, session logic (mocked hardware), and device API verification. Add `-k` or `-m` filters when iterating on specific components.

---

## Troubleshooting

| Symptom | Suggestion |
| --- | --- |
| Discovery packets missing | Ensure UDP broadcasts reach the client network; set `http_advertise_host` to a routable IP. |
| Master lock denied | Confirm the websocket client ID matches your hardware family (DWARF3 vs DWARF2/Mini). |
| Exposures timeout | Check FTP connectivity to the STA IP; increase `ftp_timeout_seconds` / `ftp_poll_interval_seconds`. |
| BLE provisioning stalls | Supply `--ble-password` explicitly and verify the adapter name via `Get-PnpDevice -Class Bluetooth`. |
| RTSP preview unavailable | Install FFmpeg/AV dependencies and verify `dwarf_rtsp_port` (default 554) is reachable. |

---

## Roadmap

- Populate telescope site coordinates from settings and persist between sessions.
- Surface live pointing data (RA/Dec/Alt/Az) from websocket notifications rather than simulated motion when telemetry is available.
- Integrate RTSP preview frames into Alpaca `ImageArray` for faster plate solving.
- Expand automated tests with hardware-in-the-loop fixtures when a DWARF lab unit is available.
- Optional authentication / TLS profile for remote observatories.

---

## References

- DWARF API documentation and community research threads
- ASCOM Alpaca API specification
- NINA Alpaca integration guide
- [Bleak](https://github.com/hbldh/bleak) for BLE control
- [aiortc](https://github.com/aiortc/aiortc) and [PyAV](https://github.com/PyAV-Org/PyAV) for RTSP decoding
