# DwarfAlp gap analysis and opportunities

## Gap analysis

| Firmware capability | DwarfAlp support | Evidence | Opportunity |
|---|---|---|---|
| V3 WebSocket transport | Already supported | APK, captures, firmware protobuf | retain shared V3 path for DWARF 2/3/Mini |
| Complete device-state query `16405` | Previously partial/inferred | exact `task_center.proto` | **implemented:** typed capture/FOV/resolution/calibration decode |
| Location + calibration | Supported | exact astro schema and live testing | improve progress/result diagnostics |
| Goto/tracking | Supported | schema, captures, hardware tests | validate status transitions/model consistency |
| Exposure/live stacking | Supported | schemas, captures, FITS on storage | improve completion/retrieval latency and retries |
| FITS retrieval | Supported with fallbacks | HTTP/FTP/storage evidence | retain newest-folder and album fallbacks |
| Camera state/temperature | Partial | exact device-state schema | Priority B: expose temperature after live validation |
| Wide/guide focus states | Not decoded in `16405` subset | exact schema | Priority B: add when a client need exists |
| Schedules/panorama/voice commands | Not exposed | exact schemas | Priority C; outside Alpaca core |
| Direct motor/factory/update | Not exposed | exact schemas and binaries | Do Not Implement |

## Capability matrix

| Capability | Available | Component/API | DwarfAlp | Confidence |
|---|---|---|---|---|
| System state | yes | task-center `16405` | typed subset | VERIFIED |
| Network control | yes | WebSocket/protobuf + HTTP | supported | VERIFIED |
| Camera/preview/video | yes | Rockchip pipeline, JPEG/RTSP | camera/preview partial | HIGH |
| Capture/FITS | yes | live stacking + CFITSIO + album/storage | supported | VERIFIED |
| Exposure/gain | yes | indexed exposure, gain 0–120 | supported | VERIFIED |
| Focus/autofocus | yes | focus/astro protobuf | supported | VERIFIED |
| Mount movement/tracking/goto | yes | astro/motor/track schemas | supported | VERIFIED |
| Plate solving/calibration | yes | astrometry.net + astro schema | supported | VERIFIED |
| Stacking | yes | multiple pipeline classes | supported | VERIFIED |
| Storage | yes | exFAT, FTP, nginx, album API | supported | VERIFIED |
| Wi-Fi/Bluetooth | yes | wpa_supplicant/AP/BSA BLE | provisioning supported | VERIFIED |
| GPS/location | location yes; GPS hardware unknown | `ReqSetLocation` | manual/web location | VERIFIED/UNKNOWN |
| Time | device state/config clues | existing sync path | supported | MEDIUM |
| Logging | yes | zlog, Breakpad, log HTTP handlers | local driver logs | VERIFIED |
| Firmware update | yes | bilbo + updater | deliberately absent | HIGH |
| Diagnostics/factory | yes | factory protobuf/debug registry | deliberately absent | VERIFIED |

## Priorities

- **Priority A (implemented):** correct `16405` request/response typing and safely
  consume capture lifecycle, camera geometry, shooting mode, and calibration snapshot.
- **Priority B:** fill the remaining exact read-only state fields and CMOS
  temperature after recorded/live response validation.
- **Priority C:** schedules, panorama, and voice-assistant capabilities only when
  there is a concrete interoperability requirement.
- **Do Not Implement:** firmware update, factory calibration/tests, MCU reset or
  flashing, raw motor primitives, and dormant USB modes.
