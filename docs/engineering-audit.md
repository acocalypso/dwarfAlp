# Engineering audit (2026-07-30)

This report distinguishes code verification, simulation, protocol evidence, and physical
hardware verification. No DWARF 3 hardware was available. A safe reachability probe found
neither the configured device nor the default AP address listening on WebSocket (9900),
HTTP (8082), or FTP (21), so no physical DWARF mini commands were sent.

## Untouched baseline

| Check | Command | Result | Notes |
| --- | --- | --- | --- |
| Branch/commit | `git status --short --branch`; `git rev-parse HEAD` | `main`, `3c6a0a3d80d572b445f91ceb6f5b6f04f2df2e63`, clean | Remote `origin/main` matched. |
| Platform | `python --version`; `platform.platform()` | Python 3.12.10, Windows 11 build 26200 | Global editable environment. |
| Installed project | `python -m pip show dwarf-alpaca` | 0.1.0 editable | Development extras initially absent. |
| Generated protobuf | `git ls-files src/dwarf_alpaca/proto/*_pb2.py` | Three old generated modules tracked | No generation command; request text said untracked, but checkout was authoritative. |
| Tests before installing extras | `python -m pytest -q` | Could not run: pytest absent | Environment issue, not a source failure. |
| Existing tests after declared install | `python -m pytest -q` | 129 passed | Source still untouched. |
| Lint | `python -m ruff check .` | Failed | Numerous pre-existing findings; configuration selected every Ruff rule. |
| Format | `python -m ruff format --check .` | Failed; 33 files unformatted | Baseline retained. |
| Imports | project/server/GUI import commands | Passed | FastAPI app title: `DWARF 3 Alpaca Server`. |
| Simulation startup | `dwarf-alpaca serve` with simulation and discovery disabled | Passed | `/management/apiversions` and configured devices returned valid envelopes. |

## Runtime architecture

```text
Alpaca client
  -> UDP discovery or FastAPI management/device route
  -> device router state and Alpaca parameter validation
  -> shared DwarfSession
  -> master lock + model capability profile
  -> WebSocket command / notification, HTTP album, or FTP file
  -> physical DWARF
  -> progress/state notification and new-file identity checks
  -> FITS/JPEG decoder
  -> authoritative capture state
  -> ImageReady / ImageArray / ImageBytes
```

The CLI (`dwarf-alpaca`) offers `serve`, `start`, `guide`, and `provision`. `start`
optionally provisions via BLE, reads persisted connectivity state, preflights the
WebSocket/master lock, then starts Uvicorn. `server.build_app` configures the selected
profile and singleton session, mounts management plus Telescope/Camera/Focuser/
FilterWheel routers, and uses FastAPI lifespan for filter preload and shutdown.
`run_server` owns UDP Alpaca discovery and Uvicorn.

`DwarfSession` owns reference-counted logical connections, WebSocket bootstrap and
request serialization, master lock, clock synchronization, telescope/GOTO state,
focus state, filter discovery/control, exposure/gain resolution, dark status, capture
identity/state, FTP and album baselines, decoding, and background temperature polling.
`DwarfWsClient` correlates one outstanding request per `(module, command)` and dispatches
notifications. HTTP provides parameter configuration and album/static-file access. FTP
provides final photo/astro assets. RTSP is implemented but is not part of the final
Alpaca image path. BLE is provisioning-only.

### State ownership

| State class | Examples | Authority |
| --- | --- | --- |
| Device authoritative | Master-lock response, command result, filter notification, exposure progress, observation/device state, FTP/album file, temperature | Device response/notification/file |
| Locally inferred | Recent GOTO validity, timer fallback percentage, capture phase between device signals | Memory; explicitly non-authoritative |
| Cached | Parameter configuration, exposure/gain/filter options, temperature, last file entries | Memory, refreshed on reconnect/profile change |
| Simulated | Synthetic image, motion, focus and timestamps | Memory only when `force_simulation=true` |
| Persisted | STA IP, network mode, timezone, last BLE address and Wi-Fi password cache | `var/connectivity.json` |

The plaintext password cache remains a known security limitation. Logs sanitize HTTP
authorization/cookies, and this audit did not print addresses, identifiers, or credentials.

## History and compatibility comparison

The credible pre-mini DWARF 3 line is tag `v0.0.3` (`0e2091d`, 2025-10-15); its capture
path followed the legacy 1.2 protocol. Mini V3 started at `7c7ccd7` (2026-03-08).
`9197f55`, `3bfacfb`, and `923a98e` added profiles/filter behavior. Current `3c6a0a3`
added captured V3 messages and decoding. Legacy DWARF 3 code was extended rather than
deleted, but profile selection was scattered and tests did not explicitly prove that a
DWARF 3 instance avoided mini commands.

| Area | Previous DWARF 3 | Baseline current | Risk | Action |
| --- | --- | --- | --- | --- |
| WebSocket envelope | 1.2, device 1 | Still 1.2/device 1 for D3 | Low | Centralized and regression-tested. |
| Camera/focus open | V2 commands | V2 for D3; V3 gated to mini | Medium | Capability profile records command family. |
| Astro capture | Raw live stacking | Same | Medium | Retained; made parameter/start/file checks strict. |
| Mini V3 | Absent | 1.20/device 4, V3 open/focus and capture-time filter selection | High | Isolated in profile and tested against hardware plus app 3.4.1 bytecode. |
| Timeout handling | Timeout failure | Mini start timeout assumed success | High | Requires independent notification evidence. |
| Gain/exposure failure | Could continue/reuse | Still continued/reused | High | Capture now fails clearly. |
| Image decode | FITS plus promoted grayscale JPEG | Same | High | JPEG remains true 8-bit RGB. |

## Capability matrix

| Capability | DWARF 2 | DWARF 3 | DWARF mini | Evidence |
| --- | --- | --- | --- | --- |
| WS profile | 1.2/device 1 | 1.2/device 1 | 1.20/device 4 | Repository protocol notes/history; mini captures encoded in current source |
| Client ID | DAF2 | DAF3 | DAF4 | Repository profiles; not official public documentation |
| Camera sensor | IMX415 | IMX678 | IMX662 | Project metadata; hardware-unverified here |
| Filters | No wheel advertised | VIS/Astro/Duo-Band | Astro/Duo-Band; Dark is calibration-only | D3 official manual; Mini app 3.4.1 bytecode and user-verified UI |
| Astro workflow | Implemented, unverified | Implemented, legacy regression tests | Implemented, V3 notification decoding | Automated simulation/protocol tests only |
| Direct photo | Present, not selected for Alpaca astro capture | Present, not selected | Experimental and disabled by default | No evidence it guarantees long exposure/gain/raw output |
| FITS | Expected | Officially documented | Expected from astronomy workflow | D3 official file guide; mini hardware pending |
| Binning/frame count | Configured through feature params | Same | Same where discovered | ACK-tested mocks; physical verification pending |
| Stop | Not advertised | Not advertised | Not advertised | No distinct graceful-stop semantics proved |
| Abort | Astro stop command | Astro stop command | Astro stop command | Code/tests; physical behavior unverified |

Do not interpret this as DWARF 3 hardware verification. It is restored code coverage for
the last credible protocol family plus current regression tests.

## Capture workflow decision

| Model/workflow | Exposure | Gain | Filter | Raw/FITS | Completion | Decision |
| --- | --- | --- | --- | --- | --- | --- |
| D3 direct PHOTO_RAW/PHOTOGRAPH | Not proved | Not proved | Not proved | May be JPEG | ACK/file only | Not selected |
| D3 astronomy raw live stacking | Parameter ACK required | Parameter ACK required | Parameter ACK required | Official FITS/raw session output | ACK + new FTP/album file | Selected |
| Mini direct PHOTO_RAW/PHOTOGRAPH | Not proved | Not proved | V3 selection separate | Observed code expects JPEG | ACK/file only | Disabled by default |
| Mini astronomy raw live stacking | Parameter ACK required | Parameter ACK required | V3 ACK/notify required | Expected FITS | ACK, or V3 progress/state corroboration, then new file | Selected, hardware pending |

Official DWARF 3 documentation describes Deep Sky mode as the route for fixed exposure,
gain, filter, frame count, dark matching, stacking, and FITS output. It documents
per-session `DWARF_RAW` folders, FITS light frames, `shotsInfo.json`, and dark filenames
encoding exposure/gain/bin/temperature. Accordingly, the astronomy workflow is the
intended production path, not a workaround. Sources:

- <https://help.dwarflab.com/en/docs/DWARF-3-Smart-Telescope-User-Manual-Part1-App-Interface-Introduction?product=dwarf-3>
- <https://help.dwarflab.com/en/docs/How-to-View-and-Obtain-the-Files-on-DWARF-3>
- <https://help.dwarflab.com/en/docs/dwarf-mini-smart-telescope?product=dwarf-mini>
- <https://www.dwarflab.com/us/pages/dwarflab-app-firmware-download>

At audit time the official download page listed app 3.4.0 and mini firmware 1.1.0.1
(2026-07-30). Those versions were researched, not tested unless explicitly marked as
hardware-verified below.

## Protocol evidence

| Operation | Model | Transport/command | Evidence | Confidence |
| --- | --- | --- | --- | --- |
| Master lock | D2/D3/mini | WS system master-lock + host/slave notify | Repository API notes and tests | Confirmed by repository capture/tests |
| D3 camera open | D3 | V2 tele/wide open | Last working history and tests | Strongly inferred current firmware |
| Mini camera open | mini | V3 tele open | Current captured message schema/tests | Confirmed by capture |
| Mini focus init | mini | V3 focus 15011 | Current captured schema/tests | Confirmed by capture |
| Mini imaging filter | mini | `ReqCaptureRawLiveStacking.ir_index`: Astro=1, Duo-Band=2 | DWARFLAB app 3.4.1 decompilation | No standalone move exists; Alpaca selection is applied at exposure start |
| Mini dark filter | mini | calibration request 11045, `filter_type=3`, `cali_frame_type=0` | DWARFLAB app 3.4.1 decompilation | Separate calibration workflow; image-delivery behavior still requires hardware verification |
| Astro start/stop | D2/D3/mini | 11005/11006 raw live stacking | Vendor API notes, legacy code, tests | D3 strongly inferred; mini hardware pending |
| Start progress | mini | notify 15255/15296/15261 | Captured V3 schemas | Confirmed by capture |
| Final image | D3 | FTP Astronomy/DWARF_RAW FITS | Official file guide | Confirmed by official documentation |

Unknown fields remain represented in source protos/dynamic payload decoders and V3 raw
config payloads are logged in hex/base64 for controlled diagnostics. Production code does
not introduce commands absent from repository evidence.

## Dependency audit

| Package | Before installed/constraint | Selected | Reason/status |
| --- | --- | --- | --- |
| hatchling | build dep, unbounded | `>=1.31,<2` | Current build backend bounded by major |
| FastAPI | 0.118.0 / >=0.118.2 | 0.141.1 / `<1` | Tests/startup pass |
| Uvicorn | 0.37.0 | 0.52.0 / `<1` | Simulation startup pass |
| alpyca | 3.1.1 | 3.1.2 / `<4` | Patch update |
| httpx | 0.28.1 | 0.28.1 / `<1` | Current stable API |
| pydantic-settings | 2.11.0 | 2.14.2 / `<3` | Tests pass |
| structlog | 25.4.0 | 26.1.0 / `<27` | Major-year bound; logs pass |
| Bleak | 1.1.1 | `>=1.1.1,<3` | Avoid untested major 3 migration |
| aiortc | 1.13.0 | 1.15.0 / `<1.16` | Current compatible line |
| PyAV | 14.4.0 | `>=14,<17` | Matches aiortc 1.15 compatibility |
| NumPy | 2.2.1 | 2.5.1 on Python 3.12; `<2.3` on Python <3.12 | Preserves Python 3.10 wheels |
| OpenCV headless | 4.12.0 | `>=4.12,<5` | Avoid untested major 5 |
| protobuf | 3.20.3 pin | 7.35.1 / `<8` | Regenerated all bindings; imports/tests pass |
| websockets | 15.0.1 | `>=15,<18` | Current code compatibility verified |
| PySide6 | 6.10.0 | `>=6.10,<6.12` | GUI import verified |
| pytest/tooling | absent initially | pytest 9.1.1, asyncio 1.4, cov 7.1, Ruff 0.16 | Test environment reproducible |
| PyInstaller | 6.13.0, undeclared | `>=6.21,<7` development extra | Supported build path declared |
| grpcio-tools | absent | exactly 1.83.0 | Compiler/runtime pairing reproducible |

`uv.lock` is the application/development lock. Library metadata retains compatible ranges.
Use `uv sync --extra development --locked` for reproduction.

Context7 documentation was checked for the dependency-sensitive migrations. Protobuf's
current Python guidance supports generated code from 3.20 onward through the current
runtime window and replaces removed `MessageFactory.GetPrototype` with
`message_factory.GetMessageClass`. The websocket client now uses the modern asyncio
`ClientConnection` and `State` APIs rather than the legacy
`WebSocketClientProtocol`. FastAPI lifespan is supplied through `FastAPI(lifespan=...)`.

## Final validation

| Check | Command | Result |
| --- | --- | --- |
| Environment consistency | `python -m pip check` | Passed; no broken requirements |
| Locked resolution | `uv lock --check` | Passed; 99 packages resolve |
| Generated code | `python scripts/generate_protos.py --check` | Passed; all 18 modules current |
| Lint | `python -m ruff check .` | Passed |
| Format | `python -m ruff format --check .` | Passed; 68 files formatted |
| Full test/coverage | `python -m pytest -q --cov=dwarf_alpaca --cov-report=term-missing` | 136 passed, 1 skipped; 56% |
| Package | `python -m build` | sdist and universal wheel built |
| Wheel contents | `python -m zipfile -l ...whl` | All source protos and 18 generated modules included |
| Imports | project, generated V2/V3 modules, GUI window class | Passed |
| Simulation integration | server plus management/camera Alpaca requests | Passed; API v1, four devices, camera connect/state error 0 |
| Windows executable | documented PyInstaller command | Built with PyInstaller 6.21; hidden five-second smoke launch stayed alive |
| Mini reachability | TCP probes to configured AP/STA on 9900, 8082, 21 | All unreachable; hardware test skipped, no commands sent |
| DWARF 3 regression | device-profile and mocked session tests | Passed; legacy 1.2/device-1 path does not issue mini-only commands |

## Classified findings

| ID | Severity | Confidence | Component | Finding | Resolution |
| --- | --- | --- | --- | --- | --- |
| CAP-01 | High | Confirmed | Exposure | Failed/unknown exposure silently continued or reused an old index | Strict failure; deterministic nearest option recorded |
| CAP-02 | High | Confirmed | Gain | Gain failure disabled future commands and capture continued | Strict failure; applied value recorded |
| CAP-03 | High | Confirmed | Start | Mini timeout was unconditional success | Requires changed progress/observation/device evidence |
| CAP-04 | High | Confirmed | Image | 8-bit JPEG shifted to fake 16-bit grayscale | Preserve 8-bit RGB and source metadata |
| CAP-05 | High | Confirmed | Concurrency | New exposure cancelled an active exposure | Reject overlap without touching first capture |
| CAP-06 | High | Confirmed | Filter | Virtual/unconfirmed selection could be accepted | Capture requires controllable, confirmed selection |
| CAP-07 | Medium | Confirmed | Binning/frames | Missing feature parameters were silently ignored | Required parameter/option failures stop capture |
| CAP-08 | Medium | Confirmed | File identity | Empty FTP baseline could accept an old latest file | Added capture ID, start time and `not_before` filter |
| ALP-01 | Medium | Confirmed | Capabilities | Stop and abort both advertised and mapped identically | Stop false; abort remains astro cancellation |
| ALP-02 | Medium | Confirmed | Progress | PercentCompleted absent | Added device-progress/timer-backed endpoint |
| WS-01 | Medium | Confirmed | Correlation | Same-key notification could consume pending response | Only response packet types consume primary key |
| DEP-01 | High | Confirmed | Protobuf | Old bindings forced obsolete runtime and no generator existed | Pinned generator, all bindings regenerated, stale check |
| LIC-01 | Medium | Confirmed | Packaging | Metadata MIT conflicted with repository GPL-3.0 license commit | Metadata corrected to GPL-3.0-only |
| SEC-01 | Medium | Confirmed | Persistence | Wi-Fi passwords stored in plaintext JSON | Documented; secure credential-store migration remains |
| ALP-03 | Medium | Confirmed | Errors | Many routers use HTTP errors instead of Alpaca error envelopes | Remaining compliance work; not broadly rewritten |
| HW-01 | High | Confirmed | Validation | Mini protocol profile required physical validation | Real Mini verified for discovery, master lock, time sync, camera open/close, V3 config, and exact 1-second parameter ACK |

## Remaining limitations

- Physical Mini validation covered connection and non-capturing 1-second parameter
  configuration. Actual image capture, capture-time Duo-Band application, and the
  calibration dark workflow still require controlled hardware verification.
- DWARF 3 current-firmware protocol family is inferred from the last credible working
  revision; firmware-dependent capability negotiation is not yet available.
- Mini filter selection is capture-time state, not a physical FilterWheel write. The driver
  records the requested Astro/Duo-Band choice and embeds its app-confirmed index in the next
  capture start request.
- Dark response only proves the firmware's aggregate status; temperature mismatch is not
  separately decoded by the available message.
- Album timestamps and paths vary by firmware; FTP FITS is preferred.
- The singleton/router state design limits multiple simultaneous physical devices.
- Broad Alpaca error-envelope normalization, authentication/TLS hardening, and secure
  OS-backed credential storage remain.
- Linux executable packaging was not added; the supported PyInstaller command is
  Windows-oriented.
