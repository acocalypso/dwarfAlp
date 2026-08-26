# Firmware protocol comparison

This audit compares the checked-in protocol surface with two independent primary
sources:

- the 16 exact `FileDescriptorProto` records recovered from DWARF Mini firmware
  1.1.3.2 (`firmware-analysis/metadata/bilbo-protos.pb`); and
- the command registry and protobuf request wrappers decompiled from DWARFLAB
  3.4.1 (`docs/apk-analysis/api-inventory.json`).

The descriptor artifact SHA-256 is
`4370a369cb1d151d052efbdaa8fd251658d3ced898dbe264aa01b612fa7aaf24`.
Use `tools/protocol/audit_schemas.py` and
`tools/protocol/audit_commands.py` to reproduce the comparisons.

## Inventory

| Surface | Files | Messages | Fields | Enums | Enum values |
|---|---:|---:|---:|---:|---:|
| Canonical DwarfAlp `.proto` files | 24 | 429 | 959 | 28 | 518 |
| Runtime generated compatibility facade | 10 | 287 | 649 | 13 | 50 |
| Recovered firmware descriptors | 16 | 448 | 1,089 | 20 | 98 |

After alignment, the canonical/firmware comparison finds 420 exact messages,
one ambiguous short name whose two fully qualified definitions match on both
sides, seven DwarfAlp-only compatibility messages, and 26 firmware-only
messages. There are no non-exact uniquely named shared messages. Fifteen enums
match exactly; the only value mismatches are the intentionally retained
WebSocket version enums described below. The complete field-by-field result is
in [firmware-schema-audit.json](firmware-schema-audit.json), with a readable
summary in [firmware-schema-audit.md](firmware-schema-audit.md).

## Confirmed mismatches

| Area | Previous DwarfAlp interpretation | Verified firmware/app meaning | Action | Confidence |
|---|---|---|---|---|
| Command 16402 | device-mode query | switch shooting mode (`ReqSwitchShootingMode`) | remove from read-only bootstrap; use 16405 for state | VERIFIED |
| Command 16403 | switch shooting mode | switch shooting technique (`ReqSwitchShootingTech`) | correct names, payload and response semantics | VERIFIED |
| Command 16404 | generic mode switch | enter camera; nested `ClientParams.encode_type` is field 3/1 | use exact message names and fields | VERIFIED |
| Commands 10050/12036 | open tele/wide camera | set preview-quality level | stop describing these as camera open/close | VERIFIED |
| Command 11040 | get generic astro parameters | get quick-set list for a camera | use exact quick-set request/response schema | VERIFIED |
| Command 15011 | initialize focus | get saved user infinity position | use exact request/response names | VERIFIED |
| Commands 16700/16701 | two unrelated parameter request classes | both use `ReqSetExposure {uint64 param_id, int32 mode, int32 value}` | use exact type and field semantics | VERIFIED |
| Command 16703 | generic adjustment with signed ID | `ReqSetGeneralIntParam {uint64 param_id, int32 value}` | correct type/name | VERIFIED |
| Notification 15261 | generic device-state event | exclusive system-I/O task state (`ResNotifyTaskState`) | decode task ID, attributes, state and task parameter | VERIFIED |
| Notification 15264 | camera parameter state | `GeneralIntParam` | correct unsigned ID and `mode` name | VERIFIED |
| Notification 15267 | changing/mode/sub-mode | shooting-mode transition state/source/destination | correct state update semantics | VERIFIED |
| Notification 15292 | temperature only | optional CMOS temperature plus camera type | preserve presence and camera identity | VERIFIED |
| Notification 15296 | observation/capture state | sky-target-finder operation state and scene type | do not use it as exposure completion evidence | VERIFIED |
| Notification 15288 | absent from DwarfAlp registry | long-exposure progress (`LongExpPhotoProgress`) | add exact command name and decode total/exposed time | VERIFIED LIVE |
| V3 camera disconnect | send legacy command 10001 and wait for `ComResponse` | V3 app PCAPs never send 10001; live Mini ignored it and emitted no response | make Alpaca camera disconnect local-only; global task/session ownership remains intact | VERIFIED LIVE |
| Motor joystick | extra field 3 `speed` | only angle field 1 and vector length field 2 | remove the unverified extra wire field | VERIFIED |
| `ReqPhoto` runtime facade | x/y/ratio fields | empty request | send an empty request | VERIFIED |
| `ReqGotoDSO` | fields 1-3 only | adds `goto_only` field 4 and optional rotation field 5 | add fields without changing existing defaults | VERIFIED |
| Panorama upload notification | ID 15246 | APK registry assigns the same name to 15245 | correct unused constant | HIGH |

Three shared schemas need special treatment. The current `ResGetDeviceStateInfo`
is a partial snapshot with a different nested type graph; the firmware's
`task_center.proto` definition is authoritative for new decoding. The current
shooting-schedule lock/replace responses assign `code` to field 2, while the
firmware assigns password/replaced IDs to field 2 and `code` to field 3. These
are wire-breaking and must use the firmware definitions.

## Evidence conflict

The embedded firmware `base.proto` declares WebSocket version 2.3. Real DWARF
Mini traffic and the current official app profile use 1.20, while legacy
profiles use 1.2. DwarfAlp therefore continues to obtain version/device ID from
the selected device profile. The embedded enum is documented but is not used to
override captured working traffic.

Command 15255 is named `CMD_NOTIFY_WAIT_SHOOTING_PROGRESS` by the APK, but its
payload is not linked to a generated app handler in the current evidence. The
two-int progress decoder remains capture-derived and provisional.

## Transport and correlation

Each WebSocket binary message contains exactly one protobuf `WsPacket`. There
is no additional length prefix, magic, CRC, or sequence number inside the
WebSocket frame. `WsPacket` carries version, device ID, module ID, command ID,
packet type, payload bytes and client ID. The protocol has no request or
transaction ID; responses are correlated by `(module_id, command_id)`.
Consequently DwarfAlp correctly permits only one pending request for a given
pair and separately dispatches type-2 notifications. Alternate response keys
are retained for commands whose completion is emitted under a notification ID.

## Call surface reviewed

The session has 42 request sites covering 35 distinct command IDs. They map to
connection/bootstrap, master lock, time/timezone, camera open/close, preview
quality, device state, location/calibration, autofocus/focus, joystick/stop,
goto/one-click goto/abort, exposure/gain/filter/frame count, quick sets,
live-stack start/continue/stop/go-live, dark check, raw photo, feature
parameters and temperature/state notifications.

Coordinate units for the supported goto and calibration calls are direct
protobuf `double` values: RA is converted from Alpaca hours to degrees at the
public boundary, Dec/lon/lat remain degrees. Exposure is converted through the
device parameter catalogue rather than guessed fixed-point scaling. Focus is a
firmware-reported integer position. No descriptor-only evidence justifies
changing those existing conversions.

## Implemented corrections

1. Canonical generated schemas now use the recovered task-center, quick-set,
   camera-parameter, focus, motor and notification descriptors. Historical
   Python names are compatibility aliases over generated classes.
2. Startup uses read-only command 16405; camera entry and shooting mode/tech
   use the verified 16402/16403/16404 payloads and state transitions.
3. Runtime handling is corrected for commands 11040, 15011, 15261/64/67/92/96
   and 16700/01/03. Preview-quality commands are no longer treated as camera
   open commands. V3 camera disconnect no longer sends the legacy command 10001.
4. The unverified joystick field and `ReqPhoto` fields were removed. Existing
   Alpaca-facing units and APIs remain stable.
5. Golden tests cover exact payload bytes, envelopes, optional presence,
   one-of state notifications and representative response decoding.

The complete command-name comparison is in
[firmware-command-audit.json](firmware-command-audit.json) and
[firmware-command-audit.md](firmware-command-audit.md). Deprecated aliases are
retained for source compatibility but are not used by the runtime. The same
audit verifies all 123 APK response/error codes numerically; all match, with
`OK` retained as an alias of the app's `WS_OK` value zero.

## Live Mini validation

On 2026-08-26, a DWARF Mini at `192.168.178.90` was tested indoors without
motor movement, autofocus, calibration or GoTo. BLE configuration and command
16405 both returned code zero. Two consecutive 1-second, gain-60, Astro-filter
captures each reached raw frame count one, produced a 1,846,080-byte FITS,
were retrieved over FTP and decoded as 1280x720 `uint16` images. Firmware code
`-11513` remained non-fatal, as previously confirmed by DWARFLAB engineering.

The live trace confirmed notification 15288 as `LongExpPhotoProgress` with
`total_time=1.0`. It also confirmed that command 10001 neither returns a
`ComResponse` nor changes the Mini's V3 shooting mode or stream. All available
V3 app PCAPs omit 10001. Camera-only Alpaca disconnect is therefore local-only;
master-lock release still completed successfully at session shutdown.
