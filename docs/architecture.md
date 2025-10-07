# DWARF 3 Alpaca Server Architecture

## Overview

The DWARF 3 Alpaca server bridges ASCOM Alpaca clients to a DWARF 3 smart telescope. It multiplexes several device-facing transports (websocket, HTTP/JSON, FTP, RTSP, BLE) behind a FastAPI application that exposes Alpaca Telescope/0, Camera/0, Focuser/0, and FilterWheel/0 endpoints.

```
+------------------+  UDP 32227  +------------------+  WS/HTTP/FTP/RTSP/BLE  +---------------+
| Alpaca Clients   | <---------> | Alpaca Server    | <--------------------> | DWARF 3 Unit  |
| (NINA, Voyager)  |    HTTP     | (this project)   |                        |               |
+------------------+             +--------+---------+                        +---------------+
                                          |
                                          v
                                     DwarfSession
                                          |
                     +-----------+--------+------+-----------+---------+
                     |           |               |           |         |
                DwarfWsClient  DwarfHttpClient  DwarfFtpClient  DwarfRtspClient  DwarfBleProvisioner
```

## Component map

| Area | Responsibilities |
| --- | --- |
| `src/dwarf_alpaca/server.py` | Builds the FastAPI app, registers Alpaca routers, configures structured logging, and coordinates the discovery service lifecycle. |
| `src/dwarf_alpaca/discovery.py` | UDP discovery responder that advertises device metadata and the correct server URL. |
| `src/dwarf_alpaca/cli.py` | Command-line interface for `serve`, `start`, `guide`, and `provision`. Handles BLE provisioning, connectivity checks, master-lock preflight, and logging. |
| `src/dwarf_alpaca/devices/` | Alpaca routers for telescope, camera, focuser, and filter wheel. Each router translates Alpaca verbs to methods on `DwarfSession` and manages Alpaca state caching. |
| `src/dwarf_alpaca/dwarf/session.py` | Central orchestrator maintaining connections, state, caches, filter definitions, and background tasks (temperature monitor, FTP polling). |
| `src/dwarf_alpaca/dwarf/*.py` | Transport clients (`ws_client`, `http_client`, `ftp_client`, `rtsp_client`), BLE workflow, exposure resolver, and persistent state helpers. |
| `src/dwarf_alpaca/config` | Pydantic settings with environment/YAML overrides. |
| `src/dwarf_alpaca/management` | Alpaca management endpoints and health checks. |
| `tests/` | pytest suite with fixtures for discovery, CLI flows, and device endpoint behaviour.

## DwarfSession responsibilities

`DwarfSession` wraps the transport clients and acts as the shared façade consumed by device routers:

- Lazily connects to the DWARF websocket and acquires the master lock, guarding access with async locks and reference counts per logical device.
- Tracks telescope slews, manual axis rates, joystick activity, and recent go-to targets to validate exposures.
- Manages camera state: exposure parameters, active capture task, FTP/album baselines, filter selection, gain tables, and temperature readings.
- Processes websocket notifications (focus, temperature, system status) and exposes cached values for Alpaca GET requests without extra network churn.
- Hosts background tasks (e.g., temperature polling loop) and ensures they are restarted on reconnect.
- Provides domain-level methods (`telescope_slew_to_coordinates`, `camera_start_exposure`, `set_filter_position`, `focuser_move`, etc.) that precisely match Alpaca device needs.

## Device routers

- **Telescope (`devices/telescope.py`)** – Implements `ITelescopeV3` verbs. Handles connection toggles, slews, tracking, manual axis motion, UTC adjustments, and error translation for DWARF astro commands.
- **Camera (`devices/camera.py`)** – Maps Alpaca camera verbs to DWARF capture flow: gain/exposure index management, dark library validation, astro capture start/stop, and image delivery via FTP/album downloads. Also exposes sensor metadata, temperature, and state transitions.
- **Focuser (`devices/focuser.py`)** – Supports relative moves, halts, and connection state tied to DWARF focus notifications. Includes safety around concurrent motion tasks and range limits.
- **Filter wheel (`devices/filterwheel.py`)** – Loads filter definitions during startup, synchronises positions, applies IR-cut toggles, and exposes focus offsets for Alpaca clients. Integrates with `preload_filters()` in the FastAPI lifespan hook.
- **Shared utilities (`devices/utils.py`)** – Common Alpaca response helpers, parameter coercion, and request context binding for consistent logging.

## Transport clients & helpers

- **`DwarfWsClient`** – Maintains a persistent websocket connection, correlates requests/responses, dispatches notifications, and implements ping keep-alives. Raises `DwarfCommandError` for non-zero DWARF error codes.
- **`DwarfHttpClient`** – Wraps DWARF REST endpoints with retry/backoff (album listing, parameter configs, mount status, exposure triggers).
- **`DwarfFtpClient`** – Polls the DWARF FTP server for new captures, supports astro and photo modes, and downloads final assets.
- **`DwarfRtspClient`** – (Optional) streams live-view frames using PyAV/aiortc, buffering recent frames for previews.
- **`exposure.ExposureResolver`** – Builds lookup tables from DWARF parameter configs, translating requested exposure durations and gains into firmware-specific indices.
- **`StateStore`** – Persists STA IP, Wi-Fi credentials, and failure history to `var/connectivity.json`.
- **`DwarfBleProvisioner`** – Executes the BLE provisioning handshake, issuing GATT commands to set SSID/password and listen for STA IP notifications.

## Key data flows

1. **Boot**
   1. CLI loads settings, optionally merging YAML profiles.
   2. `start` command provisions Wi-Fi (if requested), updates settings with saved STA IP, and runs a preflight session acquisition to ensure hardware access.
   3. `run_server` builds the FastAPI app, preloads filters, configures structured logging, and starts the UDP discovery responder.
2. **Discovery**
   - UDP listener waits on `(discovery_interface, discovery_port)` for Alpaca probes and replies with JSON describing the server, advertised host, and four logical devices.
3. **Connection lifecycle**
   - When an Alpaca client toggles `/connected` to true, the corresponding router calls `session.acquire(<device>)`, incrementing reference counts and lazily connecting transports. Disconnects release the device and shut down transports when counts reach zero.
4. **Slew & tracking**
   - Alpaca slews invoke `session.telescope_slew_to_coordinates`, which halts manual motions, issues `ReqGotoDSO`, records the target, and spawns tasks to monitor completion. Abort and manual axis motions map to joystick vector commands with safety limits.
5. **Focusing**
   - Relative focus moves choose between single-step and continuous DWARF focus commands based on delta magnitude while listening for `ResNotifyFocus` notifications to update absolute position.
6. **Filtering**
   - Filter names derive from DWARF parameter configs. Selecting a slot triggers IR-cut toggles and `ReqSetFeatureParams` invocations while caching focus offsets per slot.
7. **Exposure pipeline**
   - Camera exposures ensure the camera is in manual mode, map durations/gain to indices, optionally warm up RTSP, check the dark library, and start astro capture via websocket. Results are pulled from FTP/album, decoded to numpy arrays, and stored in `CameraState` for Alpaca `ImageArray`/`ImageBytes` responses.
8. **Telemetry**
   - Temperature notifications update `CameraState.temperature_c`; periodic polling keeps readings fresh. Telescope and camera states maintain timestamps to satisfy Alpaca GET semantics.

## Provisioning workflow

1. `dwarf-alpaca guide` creates a `DwarfBleProvisioner` with adapter/password hints.
2. BLE GATT operations push SSID/password, wait for STA association, and parse the reported IP.
3. On success `StateStore` updates `var/connectivity.json` with the STA IP and cached credentials. Future `start` invocations reuse this state automatically.

## Persistence & logging

- **State** – `var/connectivity.json` stores STA mode, IP, password cache, and last error. Additional runtime artefacts (last parameters, album baselines) live in memory inside `DwarfSession`.
- **Logging** – Global logging uses `structlog` JSON processors. `cli.start` adds a rotating file handler in `var/logs/dwarf-alpaca-start.log`. HTTP access logs flow through custom middleware.

## External dependencies

- `FastAPI`, `uvicorn[standard]` – HTTP server & ASGI runner.
- `structlog` – Structured logging.
- `alpyca` – Alpaca constants and helper structures.
- `httpx` – Async HTTP client for DWARF REST endpoints.
- `bleak` – Cross-platform BLE provisioning.
- `numpy`, `PyAV`, `aiortc`, `opencv-python-headless` – Image and stream handling.
- `protobuf` – Generated DWARF protocol messages.
- `pytest`, `pytest-asyncio`, `ruff` – Development tooling.

## Testing strategy

- Unit tests simulate websocket responses and FTP/HTTP interactions to validate session logic and Alpaca responses.
- CLI tests run `dwarf-alpaca` commands via subprocess fixtures and assert logging/state outputs.
- UDP discovery tests fire synthetic probes and verify payload contents and advertised hosts.
- Future work: hardware-in-the-loop regression tests once CI access to a DWARF unit is available.

## Future enhancements

- Stream live RA/Dec/Alt/Az feedback from firmware notifications instead of simulated motion when telemetry is present.
- Integrate RTSP preview frames into Alpaca camera endpoints for faster focus and plate solving.
- Expose additional Alpaca actions (e.g., park, pulseguiding, autofocus) as the DWARF API is reverse engineered.
- Harden TLS / authentication story for remote observatories and multi-user deployments.
- Build structured observability (metrics/tracing) for long-running sessions.
