# Native schedules in DWARFLAB 3.4.3

Audit date: 2026-10-18. This is static APK evidence, supplemented only where
explicitly attributed to the main audit's device tests. The APK research subtask
sent no hardware commands. The main audit separately performed the narrowly
scoped Mini queue/readback/cancellation acceptance described below.

## Artifact and method

The analyzed artifact is
`build/reverse-engineering/apk/DWARFLAB_3.4.3_apkcube/apk-set/base.apk`, SHA-256
`98f45d1f80e51923e812c5ec431e097e9f5b63ea29f95df52a0c05f7dd4cdd4f`.
Package inspection was recorded as
`ev_8a01bff6c358263b678aa9f26ed34ff9bad75c7b160658cc1310bc92b3e4c87a`.
Focused REA Android class, method, and incoming-reference inspections used JADX
headless MCP 0.7.1. Methods cited below had complete returned source; enum static
initializers used explicit smali fallback. Decompiled Java aliases are not stable
raw DEX names; the REA selector and prototype identify the inspected method.

## Four separate version facts

These values must not be substituted for one another:

| Value | Source and use |
| --- | --- |
| APK request envelope **2.7** | The 3.4.3 shared packet factory takes compile-time `BaseProto` enum numbers. |
| Device response envelope **1.8** | Observed by the main audit on the attached devices; it does not prove the required request version. |
| Device feature protocol **2.6** | The main audit read `majorVersion`/`minorVersion` from `getDefaultParamsConfig` on both devices. The app uses this version for feature gates. |
| Firmware release | Separate `fwMajorVersion`, `fwMinorVersion`, `fwPatchVersion`, and `fwBuildVersion` fields; not the feature protocol or packet header. |

`bua.a.a(WsCmd, byte[])` explicitly builds a `WsPacket` with
`WS_MAJOR_VERSION_NUMBER.getNumber()` and `WS_MINOR_VERSION_NUMBER.getNumber()`.
The inspected enum initializers assign **2** and **7** respectively. It uses the
connected hardware model ID, the module enum ordinal, command value, message-type
ordinal, serialized payload, and persisted app client ID.

Evidence:

- Packet factory `(Lcom/convergence/dwarflab/data/bean/ws/WsCmd;[B)Loj0;`:
  `ev_378fce47fa6c75eea8dae5b5dff9a3abedf1707751207472b4055c72936d50ff`.
- Major enum `<clinit>()V`:
  `ev_696ae3a1b5723adc327eb00c407700eb1d8368822c267407323b1ad93124b01b`.
- Minor enum `<clinit>()V`:
  `ev_f66f9a956311537e6b5c9e5a27c8ae8ac812d1c33ea3d9c0b6fc8f377bd437bd`.

`AppViewModel.s2(DeviceConfig)` constructs `ProtocolVersion` from
`config.getMajorVersion()` and `config.getMinorVersion()`. It separately constructs
`FwVersion` from the firmware fields. Its configuration request calls the HTTP
`getDefaultParamsConfig` API through port 8082. The historical 3.4.1 Retrofit
interface explicitly declares `GET getDefaultParamsConfig`; the main audit
successfully read that endpoint on current hardware. The 3.4.3 abstract interface
method has no executable body, so REA's method view did not itself expose its HTTP
annotation.

Evidence:
`ev_c533ec59ae1f1c42467d3fea145408be51f9d7ec609a8a19830c906bf4719fc6`,
`ev_4607a550c36d2c78aa97c4f7bbdeb5bee762ad90b6e0a98a05bd36398af23119`,
`ev_ff530a558f0211c974f1d4b75e2a5dcb1032909a7b521e29616bc111c950bd56`.

### Model and preparation gates

`ScheduleDetailVM.L(int planDeviceId)` requires host control and a matching
connected model ID. For DWARF 3, hardware ID 2, it checks
`ProtocolVersion.isSupportSchedule()`: major > 1, or major == 1 and minor >= 9.
The other branch, including DWARF 2 and Mini, checks `isSupportScheduleOfD2()`:
major > 1, or major == 1 and minor >= 7.

Requested autofocus or skipped calibration triggers an additional compatibility
dialog when the feature protocol is below **2.5**. A positive dialog action can
continue the upload; that does not establish that older firmware honors those
flags. `focusMode` and `calibrationMode` are independent of an EQ setup command.

Both devices' reported feature protocol 2.6 passes these static app gates. The
DWARF 3 schedule-list timeout therefore cannot be explained by comparing its
response header 1.8 with the 1.9 feature threshold. A request-envelope difference
was a candidate for the main audit's separate read-only investigation; static
code alone does not establish the runtime cause of a timeout.

Evidence:

- Model/ownership gate:
  `ev_d748d93af95822f48d3b7190aa0ab6b27c9f5e7559406fda64826cedb0dd31e6`.
- DWARF 3 threshold:
  `ev_6e02aa0c6799173215fe9a1b646d6102615fd3835b38d71ac8abbe53e6a1bde5`.
- Other-model threshold:
  `ev_adfbbb7b93d1dad300bb87298e6ded84e9af2b0ac1f3c36d74ef59048a92b571`.
- Preparation compatibility dialog:
  `ev_f84ede395aba6dee01fddd9d42e15932eb311876046c00791a516a57553ab9b4`.
- Protocol 2.5 constant:
  `ev_10b76b3ea7ef3e42852ee94decb1e9eb4e4fe7981259f1d42e91c17beb2cca86`.

## Time, coordinates, and task parameters

Native scheduling uses absolute UNIX **seconds**, not milliseconds or local wall
clock numbers with an offset added afterward. Android UI date helpers construct
local calendar values in the system timezone and convert them once to epoch
seconds. `d42.p(long,int,int)` multiplies the input seconds by 1000 for
`Calendar.setTimeInMillis`, sets hour/minute/second, and divides the resulting
milliseconds by 1000. UI formatter `d42.A(long)` similarly multiplies seconds by
1000 before formatting.

Evidence:
`ev_de4078b89031f9bf110e507695abb551639e1416bfb5707af52479fd5085a923`,
`ev_4f7c9cae523f84c7c1161178469275b9ef2dda0016a9b447371798721e659b6f`.
Some other date helpers explicitly accept milliseconds; their units must not be
generalized to the native schedule fields.

| Field | Observed construction |
| --- | --- |
| `scheduleTime` | Observing-date/night anchor, from the dialog's `planTime`, otherwise `AppViewModel.getStarTime()/1000`. It is independent of task execution start. |
| Outer `startTime`, `endTime` | Keep an already valid outer range; otherwise derive the minimum task start and maximum task end. |
| Nested `TaskParam.startTime`, `endTime` | Reservation curve endpoints in epoch seconds. Each task must span at least **600 seconds** in the official UI. |
| Outer `createdTime` | New-plan creation uses `System.currentTimeMillis()/1000`. |
| Outer `updatedTime` | Preserved from the stored plan; a newly constructed plan defaults to zero. |
| Per-task `createdTime`, `updatedTime`, `code` | The official upload builder does not set them; protobuf defaults are zero. |
| `ra` | Hours. Manual HMS input becomes `h + m/60 + s/3600`. Atlas radians become degrees / 15, normalized to [0,24). |
| `dec` | Signed degrees, including manual DMS conversion. |
| `shutterIndex`, `gainIndex` | Selected `NamedValue.getValue()`, not the row ordinal. Names are the corresponding `NamedValue.getName()`. |
| `filterModeIndex` | Selected `FilterType.getValue()`. |
| `count`, `stacked` | Initialized to zero. No static incoming references to `TaskParam.setCount` were recovered; they are not a proved requested frame quota. |
| `createFrom` | Passed from the UI's `createType`: manual coordinates use 2, atlas selection uses 1. |
| `paramMode`, `paramVersion` | Deep-sky mode 0 and parameter version 1 for this path. This does not establish wide-camera scheduler support. |

`scheduleTime` deserves particular care. The creation dialog initially takes the
current observing epoch; before today's sunrise it can choose the preceding
calendar date. Its `z(long,double,double)` method saves that reference as
`planTime`. It is not a required equality with the first task's start. A client
should represent this planning anchor separately rather than inventing an extra
timezone offset. Whether the firmware uses it for anything beyond organizing
the observing night requires firmware/runtime evidence.

`ScheduleDetailDialog.D0(long,long)` explicitly tests
`endTime - startTime >= 600`; shorter windows show an error dialog. A native
time-window job therefore must not promise an exact number of frames.

Evidence:

- New-plan creation and seconds:
  `ev_164a23f0e9bd515888d426ebd399bae7cc879ef904cd156f13c2edbab4bcfb7d`.
- Planning anchor:
  `ev_7f3d3ba27cbd5ea4f4e22142836151dca541f0d1dfc7ca4d0cab3f9a1847a6c8`,
  `ev_ef37b310a604a7f19970365067d4c75485acecdca5e3a569d06564fe3e84cdb9`.
- Outer range derivation:
  `ev_202025c96e8cef2bd54ca34aaf67151ebe36921fb8b39de4776683addbcc9ca1`.
- Task endpoint assignment:
  `ev_1cabab51f2726608bc3f07281dd94d3b7f91e5b63875916a64777acbcb042f61`.
- Minimum duration:
  `ev_28d92df9a16b8fa9a1b38656e36bf7a35acbbeef0f12dc99e280e51b50547408`.
- Coordinate/value selection:
  `ev_cd1548cb4718884e6a63f5661b7d5ed650dbce4ea7a8940b072716ed0da128f4`,
  `ev_4e7213f657e3b04153f7ccf7d45cec788ee96001c300fef2f937c8d3612c79e3`,
  `ev_0b6b82acf8c94dd305daea11b331dc79ed7ce390bfe08ab0f820963b569f14a9`.
- Stored task construction, explicit smali fallback:
  `ev_4562ccb651a7447878a6fbd1bb2c9cad75877fbb2001c5eb7cb93692bcbe8595`.
- Zero static incoming `setCount` references:
  `ev_1f16768b156b3fda62651559d48c9cbb239f79690ba35b8f1f5aeaebfcfc7d97`.

### Plan JSON and IDs

`PlanParam` contains `focusMode`, `latitude`, `longitude`, `cityName`, and
`calibrationMode`. `focusMode(true)` writes 1, false writes 0.
`jumpCalibration(true)` writes 1, false writes 0; thus calibrationMode 0 means
normal calibration, not an instruction to enter EQ mode. The constructor's
default calibration mode is zero.

Official IDs use a persisted **app client ID**, not the telescope MAC:

- Schedule ID: client ID + current epoch milliseconds + `.Android`.
- Task ID: client ID + current epoch milliseconds.

The native schema declares strings and does not itself prove that firmware
accepts arbitrary UUID formats. The official upload builder omits top-level
`macAddress`; responses can carry the actual device MAC. Physical target identity
must still be checked by the controlling client's discovery/session boundary.

Evidence:
`ev_b34ba9c7205f53d241afe006c06071efa182f0a5a7dc9c574ea97856fefa6af6`,
`ev_384d1baeb974fe9967acfd6bc21b1143d7fc632cb5e812ca0da795a80df9f9d2`,
`ev_8a8b42781c2c0fb5b9b706ccd1b5405aaf904861c456bf83b9463e25ce5da5c4`,
`ev_2a41f5f1fecde5171db009d7beb1ad03d66f540b2ba059f2214db1bac54ef621`,
`ev_902256e6d8c397486daba3781b1ad17842d77ee7bd28e055c23d0552f0d74833`.

## Verified static request lifecycle

1. Construct a local plan and its version-1 JSON tasks. The local unsynchronized
   plan state is 0; each task's idle state is 0.
2. The user submits the plan. `ScheduleDetailVM.V(String,int)` calls the
   ownership/model/feature-protocol gate before launching its `j` coroutine.
3. The coroutine reads the stored `ScheduleWithTask`, builds the task messages,
   derives/keeps the outer time range, and remaps outer local state **0 to 1**
   (`STATE_PENDING_SHOOT`). Sending a newly queued plan as state 0 does not match
   this official path.
4. `WsSyncShootingScheduleReq.getWsPacketByteString()` serializes
   `ReqSyncShootingSchedule { shooting_schedule: ... }`, command **16100**, module
   **13**, through the shared packet factory described above.
5. A list read is a separate empty `ReqGetAllShootingSchedule`, command **16102**,
   module **13**. `ScheduleListVM.E()` and `HomeViewModel.G()` send it directly;
   these methods contain no additional scheduler-specific unlock handshake.
6. Schedule result/state notification **15248** and task-state notification
   **15249** are separate from upload acknowledgements. An upload ACK does not
   establish that a timed job ran, that a frame quota was met, or that any image
   exists. A caller should verify the returned/read-back schedule and follow the
   device lifecycle independently.

Other native schedule operations remain cancel 16101, read by ID 16103, replace
16105, unlock 16106, lock 16107, and delete 16108. Replacement must be explicit;
the presence of conflict/replace fields is not permission to overwrite another
device job.

Evidence:

- Submission entry point:
  `ev_bb1e9787d117da0f1255efa07bf83efafb451f165646290013a6e8e414e3eab3`.
- Exact message builder/state remapping:
  `ev_e8b26e623baa4ebb48a3fdcf0be3b52226977bb59fd2289fa4ceb1d0979acd98`.
- State enum 0/1/2/3/4:
  `ev_e0caa433012d00089e03cf828c092e4c217b15c2fa2ef1d22beea5454ce17640`.
- Upload and list request serializers:
  `ev_33f78b65532e3115f5f35318ccd877c45eaa8c6e2e7ebe7d1a73f2848159897c`,
  `ev_308c9b91402aa88ee3b8bcb567c6ea2209ae3db96cd3fc33b2de4c4caa26ee7b`.
- List dispatch:
  `ev_77c6a7e40aaff860b4b66134f1c2a2b12d88f509a262eb6156b8f748518906f0`.
- Numeric command constants, including notifications:
  `ev_8124ea0200e7668a1148745859f64e3eda432027903e2442453e5c31612d2bdb`.
- Module selection and module 13 ordinal:
  `ev_ec2c70d9c5a4cb68bf97c692fcf9212b0088b34479dd93e3e7a1f0c9657cdab9`,
  `ev_5429d903f915a39d9637aab15c07702a6f46dee512bebc1c41cbd7b7ac964c31`.

## Limits and follow-up

Static gates are compatibility hints, not successful command dispatch. Matching
firmware protobuf descriptors also do not prove that a module is loaded or that
its handlers are reachable in a given runtime. The main audit recovered identical
schedule descriptors from current DWARF 3 and Mini firmware, but recorded different
behavior for the schedule-list request using the earlier client profile.

### Main audit's controlled acceptance

The main audit tested the attached Mini using the exact APK request profile,
major 2 / minor 7 / hardware device ID 4. The SDK builder produced one future
task with a 600-second window and schedule state 1. Submission followed by
`getAllShootingSchedule` readback confirmed that the exact test ID was queued.
The main audit immediately cancelled that future plan; a subsequent read showed
the test ID removed and the original completed schedule history preserved.
Control was released afterward. No scheduled exposure or motion began during
this test, and actual timed execution was not tested.

The private raw record is `audit/evidence/mini-schedule-write-20261018.json` in the
workspace root. It contains device-specific data and is deliberately not copied
into this public note or used as a public fixture. This result establishes
controlled Mini upload/readback/cancellation for that tested build and input; it
does not establish future execution, arbitrary ID-format acceptance, or every
possible recipe.

On the subsequently reconnected DWARF 3, direct fresh-ID sync initially failed
with -16301 (invalid shooting duration). Comparing Steve's astro_dwarf_session
and dwarf_python_api exposed the same boot-clock problem. Setting UNIX time,
site UTC offset and IANA timezone before sync resolved the rejection.

The SDK fresh-ID path then queued a future whole-minute 600-second test plan.
Exact per-ID readback confirmed pending state; the full list replied while the
plan existed. Cancellation succeeded and per-ID readback returned -16305,
confirming removal after the successful cancel ACK. Control was released and
no task executed. The actual Dwarfium queueTimedObservation service was tested
separately with automatic clock preparation and the same queue/list/cancel
results. Private evidence: audit/evidence/dwarf3-app-schedule-20261018.json.

The SDK now enforces whole-minute windows, a ten-minute minimum, and a start
within twelve hours, consistent with Steve's implementation. Source revisions:
astro_dwarf_session 7b2e8b6e34d90c2806fd1ba49268c80f2827db82 and
stevejcl/dwarf_python_api 93ec09fff6b6dc6afffdf0d1cb2c78d2baf419ca.

Required acceptance remains actual scheduled start/stop and image retrieval
under suitable conditions, reconnect recovery, clock/DST transitions,
multiple-device isolation and long sessions. Queue/cancel success alone does
not certify unattended scheduled execution.
