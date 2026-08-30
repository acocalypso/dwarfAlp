# `bilbo` internals

`bilbo` is the 9.18 MB stripped ARMv7 executable that implements the device
runtime. This chapter combines the update-package layout, ELF imports and type
information, embedded protobuf descriptors, string cross-references, targeted
Ghidra decompilation, and the reproducible whole-program inventory. It records
derived interoperability facts; vendor binaries and decompiled bodies remain
local and ignored.

## Reverse-engineering coverage

| Surface | Result | Confidence |
|---|---|---|
| APK 3.4.1 | all split DEX files decompiled; 356 WS commands, 137 response codes, 50 HTTP operations, 11 request models, and BLE commands 1–8 extracted | VERIFIED |
| `bilbo` | ELF metadata plus 13,306 functions, 1,108 imports, 8,544 defined strings, 115,098 call edges, 32 memory blocks, protobuf descriptors, and string xrefs inventoried | VERIFIED |
| `bilbo` decompilation | targeted protocol/network/capture functions exported; a near-full C-like export attempted locally | VERIFIED attempt; names and optimized bodies remain imperfect |
| `bilbo_upgrade` | full Ghidra export completed; update manifests and MD5 path traced | HIGH |
| Update package | all 43 supplied files typed, hashed, and classified; all nested `update.json` manifests inspected | VERIFIED |
| Live Mini image | p1-p9 acquired; seven source-MD5 verified, p8/p9 retained as exact-sized live snapshots; rootfs/OEM/userdata extracted from working copies | VERIFIED with documented live-filesystem limitation |

The Ghidra `inventory` command deliberately exports derived tables rather than
source-like bodies. It makes future firmware comparisons possible without
publishing proprietary implementation code.

## Startup and ownership

The supplied `run.sh` prepares UART1 and UART3, GPIO-controlled hardware,
the exFAT media partition, USB mass-storage/RNDIS, Broadcom BLE, FTP, SSH, and
nginx. It then starts `bilbo` and `bilbo_upgrade` as separate processes.

Inside `bilbo`, recovered initialization symbols show this ownership pattern:

1. Load the model/version configuration and initialize singleton services.
2. Initialize Rockchip media, tele/wide camera devices, encoder parameters,
   motor/RGB controllers, MCU UART, and persistent settings.
3. Create WCDB tables and seed picture, burst, video, panorama, astronomy,
   calibration-frame, scheduling, and parameter state.
4. Start astronomy, album, scheduling, timer, HTTP, WebSocket, JPEG-preview,
   and RTSP workers.
5. Dispatch protobuf requests into module-specific state machines and publish
   asynchronous state/progress notifications.

The exact source-level ordering inside optimized startup code is not completely
recoverable, but the service ownership and worker boundaries are independently
visible in symbols, imports, schemas, and configuration.

## Runtime services

| Service | Interface | Recovered responsibility |
|---|---|---|
| WebSocket control | TCP 9900, binary protobuf `WsPacket` | commands, correlated responses, notifications, client/master ownership |
| Device HTTP | TCP 8082 | album metadata and FITS discovery/deletion, shooting-mode metadata, media lookup, firmware-support endpoints |
| Raw-JPEG HTTP | TCP 8085 | libhv route `/raw_jpg?stack=...&bits=...` |
| JPEG guide stream | TCP 8092 | lower-level `JpgServer`/`sendCamGuideStream` transport |
| RTSP | TCP 554 | encoded camera stream lifecycle |
| nginx | TCP 80, separate process | static media/UI access rooted on the mounted device storage |
| WCDB/SQLite | local `device.db` | media album records, astronomy FITS rows, settings, schedules, and runtime state |
| Camera/media | Rockchip MPI/RKAIQ, V4L2, FFmpeg | sensor setup, raw/YUV/JPEG/video acquisition and encoding |
| Astronomy | OpenCV, CFITSIO, astrometry/WCS, RKNN | calibration, plate solving, goto/tracking support, stacking, FITS/WCS output, thumbnails |
| Motion/focus | UART/MCU and motor abstractions | axes, filter/focus movement, tracking, dithering, limits, notifications |

Confirmed device HTTP routes in this firmware include:

- `POST /album/astro/fitsList`
- `/album/astro/deleteFits`
- `/album/getMediaInfoByFilePath`
- `/shootingMode/getSupportedShootingModes`
- `/shootingMode/getParamAndSetting`
- `/mcufirmwareVersion`

The APK inventory supplies the HTTP verb and request model where the stripped
firmware call site does not preserve a readable method constant. DwarfAlp uses
the confirmed `POST` form of `fitsList`.

## Astronomy capture pipeline

The recovered implementation separates control from image transport:

1. Parameter commands update exposure, gain, resolution, filter, and capture
   count in the active parameter namespace.
2. The live-stacking start command carries filter and force-start state; it does
   not replace the preceding parameter commands.
3. `Astro` coordinates tele/wide acquisition and invokes `ImageProcessor`
   live-stacking pipelines. Separate functions exist for light, dark, and newer
   calibration-frame workflows.
4. State and progress are emitted through notification commands while raw and
   stacked products are written beneath the astronomy media tree.
5. CFITSIO writes the FITS product and WCS metadata; WCDB album rows index the
   result. The HTTP FITS-list operation exposes the completed file to clients.

This explains why DwarfAlp must wait for terminal capture state and then poll
the album API: a successful WebSocket response acknowledges workflow start, not
availability of the final FITS file. It also supports the existing strategy of
retrieving the device-generated FITS rather than reconstructing it from the
JPEG preview.

## Calibration, goto, and tracking

`Calibrater`, `Goto`, and `Astro` are distinct cooperating components. Recovered
functions include gyro-assisted calibration, equatorial solving, sky-target
finding, motor-path goto, sidereal/solar-system tracking, guiding, dithering,
and field-derotation workers. The protocol therefore reports several stages;
the initial command response alone cannot establish success.

DwarfAlp must continue to use the asynchronous calibration and tracking
notifications as authoritative completion signals. A non-zero task-manager or
scheduler response now appears by symbolic name in driver errors, including
the newly recovered `CODE_GLOBAL_TASK_MANAGER_BUSY` (`-16600`).

## Persistence and files

The firmware contains ORM/type evidence for `astro_info`, `astro_fits_info`,
multi-stack, mosaic/subview, picture, burst, video, scheduling, calibration
frames, common parameters, and auto-parameter state. The acquired live
`/userdata/data/device.db` confirmed the corresponding tables and columns,
passed `PRAGMA quick_check`, and was inspected only for row counts and
non-secret runtime settings. Astronomy rows retain
the requested exposure, gain, filter, target, RA/Dec, frame counts, FITS
path/name/MD5/size, stack state/code, location, equatorial mode, and rotation.

The database resolves parameter layers that were previously inferred only from
notifications: `param_type` 0 is default/base, 1 is saved normal state, and 2
is current/runtime state. The DSO tele current row captured the same one-second,
gain/filter/count operating values used during live driver testing.

The media partition is `/dev/mmcblk0p10`, mounted at `/DWARF_mini` in this Mini
bundle. Internal working paths also include `/userdata/astro/tele` and
`/userdata/astro/wide`. These paths are firmware implementation details and
must not be assumed to be identical across models or releases.

## Live autofocus and goto trace

Retained Bilbo logs show that one-click DSO goto enables auto-calibration,
constructs `FocusWrapperAstro`, checks user/factory infinity positions, resets
or positions the focus motor, applies autofocus exposure/gain/filter state, and
then continues calibration and goto asynchronously. Error `-14511` is emitted
after the controller reports `StepMotor 3 need reset`; it is a focus-stepper
reset failure rather than a plate-solving response.

## Update and trust boundaries

`bilbo_upgrade` is a separate process. Nested manifests select target paths,
directory/file treatment, executable bits, and MCU versions. Its recovered
path validates staged files against MD5 values from the update metadata before
installation. The SHA256/RSA routines found in `bilbo` are called by cloud
activation operations, not by the observed updater path. Whether an outer
package signature is verified before staging remains unresolved; this project
does not bypass or modify any integrity mechanism.

## Driver-relevant conclusions

- Treat WebSocket success as workflow admission, not image completion.
- Preserve parameter-setting order and active namespace discovery.
- Fetch the authoritative FITS through the album HTTP API after completion.
- Decode and log firmware error names as well as their integer values.
- Coordinate capture, calibration, goto, and scheduling through their shared
  global task state; `-16600` explicitly identifies task-manager contention.
- Keep device/model capability claims separate from commands merely registered
  by the app.

## Reproduction

From the repository root, after supplying authorized artifacts:

```powershell
docker compose -f tools/reverse-engineering/compose.yaml run --rm analyzer apk
docker compose -f tools/reverse-engineering/compose.yaml run --rm analyzer firmware
docker compose -f tools/reverse-engineering/compose.yaml run --rm analyzer `
  inventory /input/extracted/dwarf_mini_v1.1.3.2/bin/bilbo bilbo-inventory
docker compose -f tools/reverse-engineering/compose.yaml run --rm analyzer `
  triage /input/extracted/dwarf_mini_v1.1.3.2/bin/bilbo bilbo-triage
```

Generated files remain under ignored `build/reverse-engineering/` paths.
