# DWARF Integration Plan

This document sketches the bridge between the Alpaca device routers and the real DWARF-II/III hardware API described in `DWARF API2.txt`.

## Runtime building blocks

- **DWARF protobuf bindings**
  - Import the request/response messages for camera, focus, motor, and system commands (e.g. `ReqMotorRun`, `ReqPhoto`, `ReqManualSingleStepFocus`, `ComResponse`).
  - Extend `src/dwarf_alpaca/proto` with the official `.proto` definitions (`motor_control.proto`, `camera.proto`, `focus.proto`, `system.proto`, `base.proto`) and regenerate Python modules using `protoc`.
  - Provide a thin façade (`dwarf/messages.py`) with helper builders and error-code utilities to decouple the routers from raw protobuf usage.

- **WebSocket transport**
  - Implement `DwarfWsClient` in `src/dwarf_alpaca/dwarf/ws_client.py` to manage a single persistent connection to `ws://<device-ip>:9900` and marshal `WsPacket` envelopes.
  - Responsibilities:
    - Encode request packets (module id, command id, request proto bytes, `MessageTypeId.TYPE_REQUEST`).
    - Await response packets (`TYPE_REQUEST_RESPONSE`) matching the tuple `(module_id, cmd)` and surface structured results; apply the error-code table from `protocol.proto`.
    - Dispatch asynchronous notifications to subscribers (e.g. focus position updates, tracking state).
    - Handle reconnect/backoff, heartbeat (`ping`/`pong`), and graceful shutdown when the Alpaca device disconnects.
  - Provide a coroutine-friendly interface: `await ws_client.send_request(module_id, cmd, message)` returning decoded response proto.

- **State/cache layer**
  - Create `DwarfSession` in `src/dwarf_alpaca/dwarf/session.py` that wraps the websocket client plus the existing HTTP client (`DwarfHttpClient`).
  - Responsibilities:
    - Track connection lifecycle (open on first device connect, close when all devices disconnect).
    - Expose domain-specific methods used by Alpaca routers (e.g. `slew_axes`, `halt_motion`, `start_exposure`, `fetch_latest_image`, `set_focus_direction`).
    - Maintain cached status from notifications (mount position, focuser steps, camera busy state) to answer synchronous Alpaca GETs without extra network churn.

## Telescope mapping

- **Connect/Disconnect**
  - On `/connected` PUT true: ensure `DwarfSession.connect()` establishes the WebSocket, fetch baseline mount status via HTTP (`/v1/mount/status` if available) and populate `TelescopeState`.
  - On false: request `CMD_STEP_MOTOR_STOP` for both axes, `CMD_TRACK_STOP_TRACK` if tracking was enabled, then close the session when camera/focus also offline.

- **Slewing**
  - Map Alpaca `/slewtocoordinatesasync` to an RA/Dec GOTO routine:
    - Convert RA hours/Dec degrees to the DWARF coordinate space.
    - Use motor or astro commands depending on firmware support:
      - Preferred: `CMD_ASTRO_START_GOTO_DSO` / `CMD_ASTRO_STOP_GOTO` when polar alignment and sky coordinates are required.
      - Fallback: compute alt/az deltas and issue `ReqMotorRun` for axis 1 (rotation/az) and axis 2 (pitch/alt) until target is reached, monitoring notifications for position.
    - Track the outstanding slew inside `TelescopeState`, flag `slewing=True` until the response signals completion (response `code == 0`) or a limit error.

- **Axis/Rate control**
  - Implement Alpaca rate setters by emitting `CMD_STEP_MOTOR_CHANGE_SPEED` / `CMD_STEP_MOTOR_CHANGE_DIRECTION` with requested rates; keep responses cached for subsequent GETs.
  - `/abortslew` translates to `CMD_STEP_MOTOR_STOP` for both axes.

- **Status polling**
  - Use notification feed or periodic HTTP polls to update RA/Dec, Alt/Az, SideOfPier, tracking status. Expose values via the Alpaca GET endpoints instead of simulated math.
  - When notifications are unavailable, schedule a `DwarfSession.poll_mount_status()` task every ~2 seconds while connected.

- **Tracking**
  - `/tracking PUT true` -> `CMD_TRACK_START_TRACK`; `/tracking PUT false` -> `CMD_TRACK_STOP_TRACK`.
  - Update `tracking_rate` based on supported rates (DWARF defaults to sidereal only); return `[0]` for `trackingrates` if no alternative speeds.

## Camera mapping

- **Connection lifecycle**
  - `/connected` true -> ensure telephoto camera is powered via `CMD_CAMERA_TELE_OPEN_CAMERA` (set initial binning/codec parameters from defaults).
  - `/connected` false -> `CMD_CAMERA_TELE_CLOSE_CAMERA` and release any pending exposures.

- **Exposure flow**
  - `/startexposure` with duration/light flag -> issue `ReqPhoto` (CMD 10002). When zoom is requested, populate optional `x`, `y`, and `ratio` per §4.7.10.2. Monitor camera function notifications (function_id `2`) to confirm completion before fetching image data.
  - Before triggering a photo, ensure the camera is in manual exposure mode and publish the requested duration by translating Alpaca seconds into DWARF exposure indices. Fetch `params_config.json` via `GET /getDefaultParamsConfig` to build a lookup table, fall back to `ReqGetAllParams` if live firmware exposes the mapping. Apply the closest supported index via `ReqSetExpMode` (manual) and `ReqSetExp`.
  - `/abortexposure` -> `CMD_CAMERA_TELE_STOP_BURST` (if continuous) or the dedicated abort command when the firmware exposes one. Clear cached image on success.
  - `/camerastate` -> derive from DWARF camera status notifications (`Cmd_NOTIFY_CAM_FUNCTION_STATE`) or fall back to timers if not delivered.
  - `/imageready` -> prefer album notifications/files when available; `/imagebytes` should request the freshly captured asset, e.g. download from HTTP JPEG endpoint (`/mainstream`) for previews and use `album/list` + `build_jpeg_url` for the persisted photo path.

- **Parameters**
  - Implement binning, gain, and exposure getters/setters by proxying to the appropriate `CMD_CAMERA_TELE_SET_*` commands with structured `CommonParam` payloads.

## Focuser mapping

- **Connect**
  - `/connected` triggers `CMD_CAMERA_TELE_OPEN_CAMERA` implicitly if focuser requires camera powered; otherwise just ensure websocket active.

- **Relative moves**
  - Map `/move` delta sign to `ReqManualSingleStepFocus` or `ReqManualContinuFocus`:
    - For small deltas, loop single-step commands (`direction=0` far / `1` near) repeated `abs(delta)` times.
    - For larger motions, start continuous focus, sleep until near target, then stop.
  - Update `position` based on notifications (`CMD_NOTIFY_FOCUS`) or local counter in absence of telemetry.

- **Halt**
  - Translate `/halt` to `CMD_FOCUS_STOP_MANUAL_CONTINU_FOCUS` and cancel local movement tasks.

- **Autofocus hooks**
  - Optionally wire Alpaca `Focus` actions to `CMD_FOCUS_START_ASTRO_AUTO_FOCUS` when the client requests autofocus operations.

## Testing strategy

- Create asynchronous unit tests using `pytest-asyncio` with a fake websocket server that asserts correct module/cmd IDs and payloads.
- Add integration tests that stub DWARF responses (success and error) to ensure Alpaca endpoints drive the expected commands and surface errors back to clients.
- Provide end-to-end smoke scenario: connect telescope, start slew, simulate completion notification, verify Alpaca state transitions and HTTP responses.

## Documentation updates

- Expand README with setup steps: generating protobufs, configuring device IP, running the Alpaca server, and testing with N.I.N.A.
- Add troubleshooting guide for common DWARF error codes and how they appear in Alpaca responses.
