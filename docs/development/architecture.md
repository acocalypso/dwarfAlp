# Architecture

DWARF Alpaca is one FastAPI process exposing one configured physical or simulated
DWARF as Alpaca Telescope/0, Camera/0, Focuser/0, and, where supported,
FilterWheel/0.

```text
Alpaca client
  +-- UDP 32227 discovery ----------> DiscoveryService
  `-- HTTP Alpaca request ----------> FastAPI device/management router
                                        |
                                        v
                                  shared DwarfSession
                           +------------+-------------+
                           |            |             |
                       WebSocket       HTTP           FTP
                    commands/notifies parameters   final files
                           |            |             |
                           `------------+-------------'
                                        |
                                  physical DWARF
```

## Entry points and lifecycle

- `dwarf-alpaca` calls `dwarf_alpaca.cli:main`. `serve` starts directly; `start`
  can provision, load persisted connectivity, preflight the master lock, and start.
- `dwarf-alpaca-gui` and `run_gui.py` create the PySide6 control center. Its
  background server uses the same app/session code.
- `server.build_app` selects a `DeviceProfile`, configures the session singleton,
  mounts management and device routers, preloads filters during FastAPI lifespan,
  and shuts the session down on exit.
- `server.run_server` owns Uvicorn and the optional UDP discovery context.
- Discovery replies with the configured HTTP URL. Device metadata comes from the
  same active profile as management endpoints.

## Device and protocol capabilities

`device_profile.py` is the centralized static capability source:

- `DeviceProfile`: identity, client ID, camera, protocol, capture, and filters.
- `ProtocolProfile`: WebSocket version/device ID and V2/V3 command families.
- `CameraProfile`: sensor geometry, pixels, binning, gain/exposure bounds and raw
  metadata.
- `CaptureCapabilities`: selected workflow, FITS, binning/frame/progress, stop and
  abort truthfulness.
- `FilterCapabilities`: labels, control path, and discovery support.

Profiles are starting evidence, not runtime proof. Parameter configuration and
notifications refine runtime filter/exposure/gain options. DWARF 3 remains on the
legacy 1.2/device-1 family. DWARF mini uses 1.20/device-4 and V3 camera/focus
messages. A model is never silently migrated to the other command family.

## DwarfSession

The singleton session is the domain boundary used by every router. It owns:

- logical-device reference counts and lazy connection teardown;
- WebSocket, HTTP and FTP clients;
- master lock and time/timezone synchronization;
- request serialization and notification dispatch;
- GOTO, tracking, manual-axis and calibration state;
- camera/focuser state and cached parameter discovery;
- filter, exposure, gain, binning and frame-count application;
- capture identity, baselines, task and phase;
- temperature monitoring and reconnect cleanup;
- FITS/JPEG retrieval and decoding.

`DwarfWsClient` permits only one outstanding request for a module/command tuple.
The session serializes device commands around that constraint. Primary correlation
keys are consumed only by response packet types; explicitly registered notification
aliases can complete commands such as master lock. Other notifications are dispatched
without disturbing pending requests.

## Capture flow

```text
IDLE
 -> CONFIGURING
 -> WAITING_FOR_DARK
 -> STARTING
 -> EXPOSING
 -> PROCESSING
 -> TRANSFERRING
 -> READY

Any active state -> ABORTING -> IDLE
Start ambiguity -> UNKNOWN
Configuration/transfer/decode error -> FAILED
```

1. The Camera router validates Alpaca duration, gain, symmetric binning and frame
   count, copies the request into the session, and rejects overlap.
2. A unique capture ID and start/file baselines are recorded.
3. The session discovers the exact firmware parameter table. Exposure and gain may
   deterministically select the nearest discrete firmware value, but command failure
   stops the capture and the applied value is recorded.
4. The selected filter must have a writable control and confirmed ACK/notification.
5. Binning, FITS format, and frame count are required feature writes.
6. For light frames, dark status is checked. Unknown, missing, or temperature-mismatched
   darks follow the app's **Continue** behavior by default; a caller or configuration
   can require failure instead.
7. Production uses raw astronomy live stacking. Direct PHOTO_RAW/PHOTOGRAPH is
   experimental and disabled by default because long exposure, gain, and raw output
   have not been proved.
8. A start ACK proves start. A mini timeout is accepted only if an independent V3
   progress, observation, or device-state value changed.
9. Firmware notification `15209.current_count` and FTP FITS discovery are watched
   concurrently. Reaching the requested raw-frame count or finding the first new FITS
   sends `11006` immediately; the later `stacked_count` is not required. FTP retrieval
   then finishes with stacking stopped. FTP is preferred, scans only the newest
   timestamped astronomy folders first, and album is fallback. A result must be newer
   than the baseline and capture start, and the selected device path is recorded in the
   capture log.
10. `15208` is the authoritative capture lifecycle (`idle=0`, `running=1`,
    `stopping=2`, `stopped=3`). A subsequent exposure waits for idle/stopped rather
    than assuming the first FITS or a `11006` response makes the camera reusable.
    Command `16405` mirrors the APK's whole-device state query and recovers a missed
    lifecycle notification.
11. FITS stays unsigned 16-bit after FITS scaling. JPEG stays genuine 8-bit RGB;
    its source format/bit depth is reported and never promoted to fake sensor depth.
12. `ImageReady`, `CameraState`, `PercentCompleted`, `ImageArray`, and `ImageBytes`
    read the same session capture state.

Graceful StopExposure is not advertised because distinct stop semantics are not
proved. AbortExposure sends the astronomy stop command and requires confirmation.

## Transport roles

| Module | Role |
| --- | --- |
| `dwarf/ws_client.py` | Binary protobuf envelope, correlation, ping, notifications |
| `dwarf/http_client.py` | Parameter configuration, album listing and static media |
| `dwarf/ftp_client.py` | Final photo/FITS discovery and download |
| `dwarf/rtsp_client.py` | Optional live preview; not authoritative final image |
| `dwarf/ble_provisioner.py` | BLE discovery, authentication and Wi-Fi provisioning |
| `dwarf/state.py` | Persisted connectivity state |
| `dwarf/exposure.py` | Firmware exposure-table parsing and deterministic selection |

## State authority

| Kind | Examples |
| --- | --- |
| Device authoritative | ACK/error, lock, notifications, temperature, new file |
| Locally inferred | Timer percentage, recent-GOTO validity, inter-signal phase |
| Cached | Parameter tables, filter options, last FTP/album entry |
| Simulated | Synthetic image/motion/focus under `force_simulation` |
| Persisted | STA IP, mode, timezone, BLE address, Wi-Fi credential cache |

The persisted Wi-Fi password cache is plaintext and is a documented security debt.
It must not be logged or included in diagnostics.

## Protobuf and packaging

All `.proto` files are sources. `python scripts/generate_protos.py` uses the exact
`grpcio-tools` development dependency, generates all bindings, and rewrites package
imports. `--check` detects missing/stale bindings. Hatchling builds the package;
PyInstaller remains the supported Windows GUI executable path. `uv.lock` is the
reproducible application/development environment.

See the [engineering audit](../research/engineering-audit.md) for evidence, history, dependency
decisions, protocol confidence, test results, and limitations.
