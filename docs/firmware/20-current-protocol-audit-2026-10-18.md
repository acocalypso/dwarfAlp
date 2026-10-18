# Current firmware protocol audit — 2026-10-18

## Scope and artifact evidence

REA inventoried the original vendor ZIPs without executing them:

| Bundle | REA retained evidence | Native application SHA-256 |
|---|---|---|
| DWARF 3 1.5.3.9 | `ev_364ff463f7256c4f639f5530a3076cd4542f9090b9940492f49c7a16475a6c5f` | `magni`: `d878e9590b109d1d970917a6ff737a1864d96139ed7245fcece19890fa684c4a` |
| Mini 1.1.4.4 | `ev_a054d897a5f34f195da40e4647cfbd07d6fa806e1fdd19cd2bac796d5c4bd7fb` | `bilbo`: `6ddad63ef4f580ed33e1b5e5e66f7bdaf583ad0c6bd74e77b344f46712900e5a` |

The original archives passed vendor MD5/size checks and ZIP CRC checks during
[acquisition](19-release-acquisition-2026-10-18.md). Extraction used the existing
path-checked `tools/firmware/Extract-Firmware.ps1`, into the ignored extraction
tree. Neither native executable was run.

## Exact embedded schema comparison

`tools/firmware/extract_protobuf_descriptors.py` recovered 16 exact serialized
`FileDescriptorProto` records from each application's bytes. Each record is
accepted only when parsing and serialization reproduce those exact bytes. The
JSON records retain source offsets, encoded lengths, SHA-256 and all fields.

All 16 descriptors are byte-identical between the new DWARF 3 and Mini binaries.
`astro.proto`, `base.proto` and `shooting_schedule.proto` are also byte-identical
to the previous Mini 1.1.3.2 baseline. Wire-schema agreement does not establish
that every model registers or executes the corresponding command handlers.

Changes from the older baseline:

- `camera.proto`: camera/focus information query plus sensor and focus metadata.
- `factoryTest.proto`: additional factory/PDAF structures. Presence is not
  authorization or justification for running calibration writes.
- `notify.proto`: additions to common progress and resolution parameter fields.
- `task_center.proto`: four new messages and camera HDR/aspect-ratio state.
- `voice_assistant.proto`: city-name metadata on voice schedule parameters.

Curated exact metadata:

- `firmware-analysis/metadata/releases/dwarf3-v1.5.3.9-protos.json` and `.pb`.
- `firmware-analysis/metadata/releases/mini-v1.1.4.4-protos.json` and `.pb`.
- `firmware-analysis/metadata/releases/descriptor-comparison-2026-10-18.json`.

The SDK preserves its original imported schema snapshots and provenance. New
release overlays have separate provenance and are applied during generation.

## Sessions and native scheduling

See the detailed [APK 3.4.3 schedule trace](../apk-analysis/native-schedules-3.4.3.md)
for class/method evidence and the exact serialization flow.

The supported-mode endpoint and APK identify deep-sky mode as **2**, Sun as
**8**. Previous SDK/application astronomy paths unconditionally selected 8;
that was a semantic mode bug even when a short exposure produced a frame.
The corrected SDK defaults DSO captures to 2 and requires explicit discovered
capabilities and matching catalogs for an intentional non-DSO mode.

Keep four version families distinct:

1. Firmware release: D3 1.5.3.9 and Mini 1.1.4.4.
2. `/getDefaultParamsConfig` feature protocol: both live devices report 2.6.
3. The APK 3.4.3 outgoing WS envelope: 2.7, actual hardware device ID.
4. Live response WS envelopes: both devices report 1.8.

The APK's feature gate uses item 2. Therefore incoming envelope 1.8 does **not**
prove that DWARF 3 lacks native scheduling support. Both live devices pass the
app's feature gate. The SDK retains the working legacy profile by default and
provides explicit version metadata rather than inferring feature support from
outgoing profile values.

Confirmed submission rules:

- New native plan state is pending-shoot **1**, not initialized/local draft 0.
- Task execution windows are absolute UNIX seconds; the app requires at least
  600 seconds per task. Convert local calendar time once, without adding a
  second timezone offset.
- `scheduleTime` is a separate observing-night/date anchor, not the execution
  trigger. Task start/end determine the actual execution window.
- Versioned schedule/task JSON is carried inside the protobuf request. Count
  and stacked values are progress, not requested frame quotas.
- The SDK checks model, physical MAC, ownership, connection generation and
  capability, never silently replaces a plan, and requires readback after ACK.

## Bounded live acceptance

Both hardware devices already ran the requested firmware at the time of this
audit. Every probe explicitly released control afterward.

Mini: a new one-task future schedule, with a 600-second window, was submitted
using the corrected SDK and exact APK envelope profile. Device readback
confirmed the queued plan. It was immediately cancelled; subsequent readback
confirmed the test ID was gone and the pre-existing completed schedule history
remained. No task was allowed to execute, and no movement or capture was started
by this test. This proves queue/readback/cancel, not unattended sky execution.

DWARF 3: the empty schedule-list request `13:16102` timed out with control held
while ordinary device-state heartbeats continued. Bounded comparisons used
legacy header device IDs 2/4 and minor versions 8/20, then the APK's exact
major 2/minor 7/device ID 2. After verifying all relevant subsystems idle, a
separate mode switch to DSO 2 was acknowledged and confirmed by a state read;
the schedule query still timed out. The D3 remains in DSO mode. No D3 schedule
was submitted because list/readback/cancellation could not be established.

The D3 runtime cause is not yet conclusively established. Focused native tracing
below found an empty-list response defect consistent with the observations.
Schema presence, an app feature gate or an ACK alone must not be presented as
successful on-device scheduling. Raw live
responses remain local under ignored `audit/evidence`; those may contain private
device/network or observing-site data.

## Native-analysis limitations

REA's Windows Ghidra adapter rejected these ARM ELF targets because its current
Windows route accepts PE and explicit raw 6502 only. Direct Ghidra 12.1.4
headless import of the D3 ARM64 executable succeeded, but automatic analysis
hit its 240-second budget. The initial string-reference export found no selected
functions in that incomplete analysis. A subsequent targeted pass recovered
function boundaries from ELF exception-frame records and followed ARM64
ADRP/ADD constant construction to the function-name strings. Directly selecting
those addresses in the saved Ghidra project produced useful decompilation:

- `getAllShootingSchedule`, `0x008e5b60` (FDE range ends `0x008e5ca0`).
  It calls the schedule query, compares the returned vector's beginning/end,
  logs and returns without a response when equal, and only otherwise calls the
  response serializer at `0x0080bb00` with command `0x3ee6` (16102), module 13,
  response type 3 and code 0. This proves a silent empty-query-result branch.
  It does not distinguish an empty database from a failed database query.
- Schedule dispatcher `0x008f22b8` explicitly routes 16102 to that function;
  the handler is present in this D3 firmware binary.
- `getShootingScheduleById`, `0x008f1b30`, sends a response even when its query
  returns an empty value, using code `0xffffc04f` (-16305). The Mini's live
  deliberately missing-ID query returned that same database-operation error.
  This is a separate read path, not proof that the D3's database is healthy.

The source executable SHA-256 above binds these linked virtual addresses to the
exact downloaded D3 release. Decompilation is recovered representation, not
vendor source. Local pseudocode remains under ignored `audit/`. The export is
reproducible using `ExportScheduleHandlers.java` on the saved headless project,
selecting the addresses above, without re-running the timed-out full analysis.

This narrows the timeout diagnosis substantially. Do not turn a timeout into
an empty queue in the SDK: transport loss or a database failure can look the
same. The SDK now also exposes explicit fresh-ID creation with internally
generated cryptographic IDs, one sync request and exact per-ID readback. It
does not automatically fall back from a timeout, infer an empty queue, accept
database errors or request replacement. A second Mini acceptance run verified
this list-independent path, then cancelled the test and preserved existing
history. Subsequently, D3 fresh-ID creation passed after initializing its clock
and timezone: exact pending readback, full list while the record existed,
cancellation and per-ID removal confirmation. The Dwarfium service path repeated
that result. No test task executed; control was released. See the native
schedule APK note for the clock prerequisite and Steve source revisions.

Remaining acceptance: actual timed
execution on sky, cancellation during execution, reconnect across scheduled
execution, resulting media, DWARF 2 hardware, and long fleet sessions.

A separate bounded live test through FleetDeviceController completed one DWARF 3
telephoto frame in DSO mode 2, with a 0.001-second exposure, gain 0 and Astro
filter. No goto/focus or forced warning continuation was used; control was
released afterward. Private capture evidence remains at
`audit/evidence/dwarf3-capture.json`. This verifies the immediate capture
session path, not native scheduled execution. Dwarfium CI passed all 55 suites /
382 tests, and its optimized production build passed.
