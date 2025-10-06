# DWARF 3 Alpaca Server Architecture

## Overview

This project exposes a DWARF 3 smart telescope to ASCOM Alpaca clients (e.g., NINA) as three logical devices: Telescope/0, Camera/0, and Focuser/0. The same server instance also performs first-run Wi‑Fi provisioning via BLE and manages connectivity fallbacks between DWARF access point (AP) mode and station (STA) mode.

```
+------------------+      UDP 32227      +------------------+
|  NINA / Clients  | <-----------------> |  Alpaca Server   |
+------------------+        HTTP(S)      |  (this project)  |
                                         +--------+---------+
                                                  |
                                                  | HTTP 8082, 8092
                                                  | RTSP 554 (DWARF)
                                                  | BLE Provisioning
                                         +--------v---------+
                                         |   DWARF 3 Unit   |
                                         +------------------+
```

## Packages and Modules

- `alpaca_server`
  - `server.py`: ASGI app (FastAPI) hosting Alpaca management and device endpoints.
  - `discovery.py`: UDP responder for Alpaca discovery (port 32227) with configurable HTTP/HTTPS advertisement.
  - `devices/`
    - `telescope.py`: Implements Alpaca `ITelescopeV3` contract backed by `DwarfMountClient`.
    - `camera.py`: Implements Alpaca `ICameraV2` with live preview and exposure capture via DWARF HTTP/RTSP APIs.
    - `focuser.py`: Implements Alpaca `IFocuserV3` for telephoto focuser controls.
- `dwarf`
  - `http_client.py`: Wrapper around DWARF HTTP API (port 8082) and JPEG downloads (port 8092) with retries/backoff.
  - `rtsp_client.py`: Async RTSP frame reader using `aiortc`/`opencv` for stream extraction.
  - `ble_provisioner.py`: BLE provisioning workflow (using `bleak`) to push SSID/password and monitor join status.
  - `state.py`: Persistence of known STA IPs and connectivity mode transitions.
- `config`
  - `settings.py`: `pydantic`-based settings for HTTP bind, TLS, BLE adapter, default credentials, timeouts.
  - `profiles.yaml`: Sample configuration for AP-first setup and STA deployments (checked into repo).
- `cli`
  - `__main__.py`: CLI entrypoint for server launch and provisioning commands (headless-friendly).
  - `provision.py`: CLI command `dwarf-alpaca provision --ssid ... --password ...` to trigger BLE onboarding.
- `management`
  - `status.py`: Aggregates telemetry (AP/STA state, last error, discovery status) for both CLI and HTTP admin page.
  - `templates/`: Minimal HTML status page rendered by FastAPI.

## Key Data Flows

1. **Startup**
   - Load configuration and persisted STA IPs.
   - Attempt STA connectivity to DWARF via stored IP; fall back to AP mode (`192.168.88.1`) if unreachable.
   - Launch BLE provisioning service to accept requests if STA fails or manual provisioning invoked.
   - Start UDP discovery responder and HTTP server.
2. **Discovery**
   - Listen on UDP port 32227, respond to Alpaca discovery packets with server description including bound scheme/host/port and device list.
3. **Telescope Control**
   - Alpaca telescope verbs map to DWARF HTTP commands (e.g., RA/Dec slews) using community-documented endpoints.
   - Maintains `Tracking` and `Slewing` state with periodic status polling.
4. **Camera Operations**
   - Live previews served from RTSP channel ch1 (wide) for pointing and ch0 (telephoto) for imaging.
   - `StartExposure` triggers DWARF capture via HTTP; upon completion, album JSON is queried for final frames (JPEG/FITS) downloaded via port 8092.
   - `ImageBytes` responses return the latest available frame in Alpaca-friendly format (e.g., 8-bit mono or color Bayer).
5. **Focuser Control**
   - Translate Alpaca focus step requests to DWARF focus increments (positive/negative). Report capabilities (absolute, reverse, temperature) per DWARF hardware.
6. **Provisioning & Recovery**
   - BLE module exposes state machines for provisioning new STA credentials and verifying connection.
   - `state.py` records last successful STA details and handles retries/backoff, falling back to AP mode as required.

## External Dependencies

- `FastAPI` + `uvicorn` for HTTP server.
- `alpyca` for Alpaca model constants and potential helper utilities.
- `bleak` for cross-platform BLE interactions.
- `aiohttp` or `httpx` for async HTTP with retries.
- `aiortc` or `opencv-python` for RTSP frame decoding; `av` library for efficient decoding.
- `pydantic` for configuration management.
- `python-dotenv` (optional) for environment overrides.

## Configuration & Persistence

- `config/settings.py` loads from environment variables, `.env`, or YAML profile.
- `var/state.json` persists STA IP, last-known mode, and last errors.
- Logging via `structlog` for consistent structured logs leveraged by NINA diagnostics.

## Testing Strategy

- Unit tests for Alpaca endpoint handlers using FastAPI test client.
- Mocked DWARF clients to validate Telescope/Camera/Focuser logic.
- Integration tests (future) using prerecorded RTSP streams and HTTP fixtures.
- Manual validation checklist aligned with acceptance criteria, documented in README.

## Open Questions / Assumptions

- DWARF HTTP endpoints support RA/Dec slew and focus control as per community examples (assumed JSON commands on port 8082).
- BLE provisioning protocol follows documented SSID/password workflow (details to implement after acquiring spec).
- Long-exposure products accessible via album API with filenames retrievable by timestamp.
- TLS termination handled externally; in-server HTTPS optional via `uvicorn[standard]` with cert paths.
