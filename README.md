# DWARF 3 Alpaca Server

An ASCOM Alpaca device server that bridges a DWARF 3 smart telescope to Alpaca clients such as NINA. The server exposes three logical devices (Telescope/0, Camera/0, Focuser/0) and coordinates DWARF-specific connectivity flows, including first-run Wi-Fi provisioning via BLE.

## Highlights

- ✅ UDP discovery responder on port 32227 advertising Telescope, Camera, and Focuser devices.
- ✅ Alpaca Management API stubbed with server description and device list for NINA enumeration.
- ✅ Telescope, Camera, and Focuser HTTP endpoints implemented with simulated behaviour ready to be wired to real DWARF APIs.
- ✅ DWARF HTTP/RTSP/BLE client scaffolding with retries, buffering, and state persistence helpers built on the official protobuf definitions.
- ✅ CLI entrypoint for serving the Alpaca API or provisioning DWARF via BLE.

## Project Layout

```
├── docs/architecture.md       # Detailed component breakdown
├── src/dwarf_alpaca/
│   ├── server.py              # FastAPI app and discovery wiring
│   ├── devices/               # Alpaca Telescope, Camera, Focuser stubs
│   ├── dwarf/                 # DWARF connectivity clients (HTTP, RTSP, BLE, state)
│   ├── provisioning/          # BLE-driven Wi-Fi onboarding workflow
│   ├── management/            # Alpaca management endpoints
│   └── config/                # Settings models and YAML loader
├── pyproject.toml             # Dependencies and CLI entrypoint
└── README.md
```

## Quick Start

1. **Install dependencies** (Python 3.10+):

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -e .
   ```

2. **Run the server** (stub mode to verify FastAPI/UDP wiring):

   ```powershell
   dwarf-alpaca serve
   ```

   The server listens on `http://0.0.0.0:11111` by default. Discovery responses advertise the same endpoint so NINA should see `DWARF 3 Telescope`, `DWARF 3 Camera`, and `DWARF 3 Focuser` once UDP broadcast is reachable.

3. **Provision DWARF over BLE** (official BLE workflow):

   You can onboard the telescope to your Wi-Fi in two ways:

   - **Interactive guide (recommended):** Scans for DWARF devices, lists nearby Wi-Fi networks, and prompts for credentials.

     ```powershell
     dwarf-alpaca guide --adapter bluetooth-adapter-name
     ```

     - Choose the BLE adapter (omit `--adapter` to use the default).
     - Pick the DWARF device from the numbered list.
     - Enter or confirm the BLE password (defaults to `DWARF_12345678`).
     - Select the Wi-Fi SSID from the discovered list or type it manually.
     - Provide the Wi-Fi password when prompted.
  - The guide remembers passwords per SSID; select the same network again and press Enter to reuse the saved password or type a new one to replace it.

   - **Direct command:** Useful for scripted environments once you know the DWARF BLE address and target SSID.

   ```powershell
   dwarf-alpaca provision --adapter bluetooth-adapter-name --ble-password DWARF_12345678 "MySSID" "MyPassword"
   ```

     Optional flags include `--device-address XX:XX:XX:XX:XX:XX` to pin the BLE connection to a specific telescope and custom BLE passwords via `--ble-password` or the `DWARF_ALPACA_BLE_PASSWORD` environment variable.

   Both flows persist the reported STA IP to `var/connectivity.json`. Review that file after a successful run to confirm the address Alpaca clients should target.

4. **Launch everything with one command** once credentials are known:

  ```powershell
  dwarf-alpaca start --ssid "MySSID" --password "MyPassword"
  ```

  - Omitting `--ssid`/`--password` reuses the most recent STA IP stored in `var/connectivity.json`.
  - When no SSID is supplied and provisioning isn't skipped, the command launches the interactive BLE guide to discover the DWARF and configure Wi-Fi on the fly.
  - Add `--skip-provision` to purely verify connectivity and start the server.
  - Customise waits with `--wait-timeout`/`--wait-interval` if the DWARF takes longer to join Wi-Fi.
  - Use `--ws-client-id` or `DWARF_ALPACA_DWARF_WS_CLIENT_ID` to supply the DWARF websocket client identifier (copy it from the DWARF log via the official toolkit if the default value doesn’t work for your unit).

  The combined command provisions (when credentials are provided), waits for the DWARF to come online, acquires the master lock, logs the IP in use, and then launches the Alpaca server. Use `dwarf-alpaca serve --config config/profiles.yaml` if you prefer to start the server without the preflight checks.

## Configuration

Settings are managed via environment variables (`DWARF_ALPACA_*`) or a YAML profile referenced with `--config`. See `config/profiles.yaml` for annotated examples.

Key options:

| Setting | Default | Purpose |
| --- | --- | --- |
| `http_host` | `0.0.0.0` | Bind address for HTTP server |
| `http_advertise_host` | `None` | Optional LAN IP to advertise via Alpaca discovery (auto-detected when unset) |
| `http_port` | `11111` | Alpaca HTTP port |
| `enable_https` | `False` | Toggle TLS (requires cert/key paths) |
| `dwarf_ap_ip` | `192.168.88.1` | DWARF AP fallback IP |
| `dwarf_http_port` | `8082` | DWARF control port |
| `dwarf_jpeg_port` | `8092` | DWARF JPEG download port |
| `discovery_port` | `32227` | Alpaca discovery UDP port |
| `state_directory` | `var` | Folder where STA state and logs persist |
| `ble_adapter` | `None` | Optional BLE adapter/device identifier |
| `ble_password` | `None` | BLE provisioning password (defaults to `DWARF_12345678` when unset) |
| `ble_response_timeout_seconds` | `15.0` | Timeout for individual BLE responses |
| `provisioning_timeout_seconds` | `120.0` | Total timeout for provisioning workflow |
| `dwarf_ws_client_id` | `0000DAF2-0000-1000-8000-00805F9B34FB` | Identifier presented to the DWARF websocket API when requesting the host/master lock. Override with the value extracted from your device logs if required. |

## Command reference

| Command | Purpose |
| --- | --- |
| `dwarf-alpaca start [options]` | Provision (optional), wait for connectivity, acquire the master lock, and launch the Alpaca server. If no SSID is provided, it automatically runs the interactive guide. Supports the provisioning flags as well as `--skip-provision`, `--wait-timeout`, `--wait-interval`, and `--ws-client-id`. |
| `dwarf-alpaca guide [--adapter name] [--ble-password value]` | Guided BLE provisioning with device discovery and Wi-Fi selection. |
| `dwarf-alpaca provision [options] <SSID> <password>` | Non-interactive provisioning when you already know the SSID/credentials. Supports `--adapter`, `--device-address`, and `--ble-password`. |
| `dwarf-alpaca serve [--config path] [--ws-client-id value]` | Starts the Alpaca FastAPI server and UDP discovery responder using the active settings (override the websocket client identifier with `--ws-client-id` if required). |

After provisioning, update your Alpaca client (e.g., NINA) to point at `http://<server-ip>:11111` (or the port you configured). The server exposes Telescope/0, Camera/0, and Focuser/0 devices that proxy commands to the DWARF hardware using the stored STA IP.

### Example Profiles (`config/profiles.yaml`)

```yaml
# AP-first bootstrap profile
bootstrap:
  http_host: 0.0.0.0
  http_port: 11111
  dwarf_ap_ip: 192.168.88.1
  dwarf_http_port: 8082
  dwarf_jpeg_port: 8092
  discovery_enabled: true

# STA deployment profile
production:
  http_host: 0.0.0.0
  http_port: 7654
  http_scheme: http
  discovery_enabled: true
  state_directory: var
  enable_https: false
```

Select a profile by passing `--config config/profiles.yaml` and exporting the desired profile name via environment variable in a future enhancement (profile loader currently overlays raw key-values).

## NINA Integration Roadmap

1. **Discovery** – Confirm UDP broadcasts reach the NINA host. Update `http_host` to the LAN IP (e.g., `192.168.1.42`) so discovery responses advertise a routable address.
2. **Telescope control** – Wire `TelescopeState` handlers to `DwarfHttpClient.slew_to_coordinates` and poll `get_mount_status` for RA/Dec feedback.
3. **Camera streaming** – Instantiate two `DwarfRtspClient` instances (wide `ch1/stream0`, tele `ch0/stream0`) and map frames into Alpaca `ImageBytes` responses, downsampling as needed.
4. **Exposure pipeline** – Replace simulated image buffer with DWARF capture requests (`trigger_exposure`) and album retrieval via `get_album_listing` plus JPEG downloads through `build_jpeg_url`.
5. **Focuser moves** – Translate Alpaca move commands into DWARF focus increments and expose capability metadata (absolute/relative, range, step size) once documented.
6. **BLE provisioning** – Fill in real GATT characteristic UUIDs and success signalling to transition seamlessly between AP and STA modes.

## Testing Plan

- **Unit Tests**: add `pytest` coverage for Alpaca endpoints using `fastapi.testclient`, mocking DWARF clients, verifying Alpaca response envelopes.
- **Discovery**: use a local script to broadcast the Alpaca discovery request (`\x00\x10\x00\x00...`) and assert the JSON response contains the expected server URL.
- **End-to-end (simulated)**: point NINA to the server IP/port manually to validate connection handshake prior to RTSP integration.
- **Hardware-in-loop**: once RTSP and HTTP integrations are wired, run NINA through slews, exposures, and focus adjustments while monitoring logs for recovery behaviour.

## Current Limitations & Next Steps

- Alpaca device implementations currently simulate behaviour; they must be connected to `DwarfHttpClient` and `DwarfRtspClient` for real hardware control.
- BLE provisioning still needs on-device testing to fine-tune retry logic and error surfacing for edge cases.
- Discovery responses advertise the bind host; override `http_host` to the LAN IP or add network interface detection.
- No authentication or TLS hardening yet; integrate mTLS or reverse proxy for production observatories.
- Protobuf stubs were generated with an older compiler; regenerate `proto/*.proto` with protoc ≥ 5 to lift the temporary `protobuf 3.20.x` pin.
- IMX678 sensor characteristics ship with placeholder gain/e⁻ tables (set to zero). Capture SharpCap Sensor Analysis CSVs for the DWARF 3 camera and update the `electrons_per_adu` and `full_well_capacity_e` arrays in `camera.py` to reflect the measured curve.

## References

- DWARF API documentation (IP modes, ports, album JSON)
- NINA documentation on Alpaca device discovery and compatibility
- Community DWARF control scripts demonstrating RA/Dec go-to operations
- Alpaca API specification (management, telescope, camera, focuser interfaces)
- Bleak (Python BLE) and aiortc/av (RTSP decoding) libraries for connectivity layers
