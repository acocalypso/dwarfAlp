# DWARFLAB 3.4.1 investigation report

## 1. Executive summary

DWARFLAB 3.4.1 (677), base APK SHA-256
`1E4F676A35EBE6F9D8CB7B3FB4720346C45C41FC41B7E7807151B0080C5DE294`,
was analyzed statically and compared with authorized DWARF Mini traffic and the
current dwarfAlp and dwarfii_api repositories. The device control plane is
protobuf over binary WebSocket on port 9900, supplemented by local HTTP on
8082, BLE provisioning and media/file transports.

The investigation confirms that Mini Deep Sky filters are Astro and Duo-Band,
selected in capture command 11005, while Dark belongs to the separate
11045/11046 calibration workflow. It also recovers calibration state/progress
commands 15290/15291 and their schemas. Production dark capture remains
disabled until image delivery is verified. A reproducible 314-command APK
inventory and evidence-indexed architecture/transport/workflow documentation
were added. Both Python and JavaScript API protobuf definitions now contain the
new notification schemas.

## 2. Baseline

See [the baseline table](README.md#baseline). The main repository began at
`729cc1f8db52d6d4925c5b37d4127cd3efd27774`; the nested API fork began at
`9644393502269b88bd11f0636f1972a7608dd92a`. Baseline Python validation was 143
passed, 1 skipped; Ruff passed; protobuf staleness checking failed because
runtime bindings were ignored.

## 3. Android application architecture

The component and state-flow analysis is in
[app-architecture.md](app-architecture.md). The essential path is UI/ViewModel
to manager/repository to `Ws*Req` protobuf builder to OkHttp WebSocket, then
command-matched response/notification handlers to observable state and UI.

## 4. Complete API inventory

[api-inventory.json](api-inventory.json) is the machine-readable registry of
314 APK commands and directly linked request builders.
[api-inventory.md](api-inventory.md) is the human-readable device-integration
subset with model, trigger, evidence and confidence.

## 5. WebSocket protocol map

[websocket-protocol.md](websocket-protocol.md) documents URL construction,
the eight-field envelope, message types, model profiles, command-based response
correlation, lock handling, liveness, reconnect and error behavior.

## 6. HTTP API map

[transports.md](transports.md#local-http) separates the confirmed local
`http://<device>:8082/` base from cloud/account APIs. Some coroutine bodies did
not decompile fully, so unresolved endpoint paths are explicitly marked
unknown.

## 7. BLE provisioning map

[transports.md](transports.md#ble-provisioning) records all eight UUIDs and the
config/scan/credential/STA workflow. GATT characteristic directions and any
segmentation/checksum mechanism await an HCI capture.

## 8. FTP and file transfer map

[transports.md](transports.md#file-and-media-transfer) documents the separation
between preview and final capture retrieval and the required stale-file guard.
No sensitive credential is published.

## 9. RTSP map

RTSP is confirmed as a preview/focus media path, not a substitute for final FITS
delivery. Model-specific URL paths and codecs remain capture-dependent.

## 10. Reconstructed workflows

[capture-workflows.md](capture-workflows.md) contains sequence diagrams for
connection, Mini light capture, dark/calibration capture and abort/recovery.

## 11. Model compatibility

The compatibility matrix is in
[model-compatibility.md](model-compatibility.md). Mini firmware 1.1.3 build 2 is
the only hardware profile verified in this investigation. DWARF 3 is not marked
hardware-verified and remains on its conservative legacy profile.

## 12. Repository gap analysis

The gap table is in
[model-compatibility.md#gap-analysis](model-compatibility.md#gap-analysis).
Important resolved gaps are capture-time Mini filter application, exact
one-second parameter support, stable Alpaca enumeration, honest workflow abort
capabilities, reproducible command inventory and clean-install protobuf
packaging.

## 13. Repository changes

| File/group | Previous behavior | New behavior | Evidence/tests |
|---|---|---|---|
| `docs/apk-analysis/*` | findings scattered across audit/probe notes | structured architecture, transports, workflows, compatibility, evidence and unknowns | APK 3.4.1 + captures |
| `api-inventory.json` and extractor | manual command lists | reproducible 314-command registry with raw symbolic expressions preserved | extractor unit test |
| Python `protocol.proto` / `v3_notify.proto` | no 15290/15291 definitions | exact state/progress IDs and three-field messages | APK embedded descriptor; protocol tests |
| generated Python bindings / `.gitignore` | ignored, stale and absent from clean package source | exact generated modules are versioned and checked | generation check and wheel build |
| nested dwarfii_api protocol, mappings and docs | no calibration notification decoding | enums, schemas, decoder/text mappings and generated output | Node fixture decode + typecheck |

## 14. Protocol definitions added or corrected

| Definition | Raw value/schema | Applicability | Confidence |
|---|---|---|---|
| Calibration state | 15290; state=1, camera_type=2, cali_frame_type=3 | app/newer profile; Mini workflow | confirmed in app code |
| Calibration progress | 15291; progress=1, camera_type=2, cali_frame_type=3 | app/newer profile; Mini workflow | confirmed in app code |
| Calibration start/stop | 11045/11046 | app/newer profile | confirmed in app code |
| Mount calibration state | 15210; state and plate-solving-attempt count | DWARF 2/3/mini shared V3 API | APK descriptor + hardware logs |
| Mount calibration result | 15256; `double azi`, `double alt` | DWARF 2/3/mini shared V3 API | confirmed in APK 3.4.1 descriptor |
| Mount calibration request | 11000; `double lon=1`, `double lat=2`; app rejects missing/(0,0) phone location | DWARF 2/3/mini shared V3 API | confirmed in APK 3.4.1 descriptor and capture call path |
| One-click calibration + DSO GoTo | 11013; RA hours=1, dec=2, target=3, lon=4, lat=5, shooting mode=6, goto-only=7, optional rotation=8; state 15233 | DWARF 2/3/mini shared V3 API | APK request class and Atlas call path; official-app Mini workflow observed successful |
| Capture filter | 11005 field 1, Astro=1, Duo-Band=2 | Mini verified | app code and hardware traffic |
| Dark filter | filter_type=3 in 11045 | calibration only | confirmed in app code; output unknown |

## 15. Test results

Main repository final validation:

| Command | Result |
|---|---|
| `uv run python scripts/generate_protos.py --check` | 18 modules current |
| `uv run ruff check .` | passed |
| `uv run pytest -q` | 147 passed, 1 skipped; one dependency deprecation warning |
| `uv run python -m build` | sdist and wheel built |
| extractor unit test | passed |
| calibration protobuf fixture tests | passed |

Nested dwarfii_api:

| Command | Result |
|---|---|
| `npm run compile-proto` | passed |
| `npm run typecheck` | passed |
| Node mapping/protobuf fixture decode | passed |
| `npm run CI` | baseline ESLint failed on 34 pre-existing project errors unrelated to this patch |

Hardware tests are opt-in and were not rerun after the static schema additions.
The existing Mini safe handshake test remains skipped by default.

## 16. Security and privacy findings

Confirmed: the manifest permits cleartext traffic and local control uses
cleartext HTTP/WebSocket. This exposes authorized LAN traffic to same-network
observation and makes master-lock correctness important. Potential concerns
include BLE credential provisioning and local file credentials, but their
framing/storage security was not sufficiently traced to assert a vulnerability.
The app requests broad Bluetooth, location, camera, storage/media, microphone,
NFC, foreground-service and network permissions, many of which serve app
features outside dwarfAlp. No live token, password, unique device identifier or
private address is included in these documents.

## 17. Unresolved findings

The unresolved list includes 11043 response semantics, dark completion and file
delivery, dark stop, unknown 11040 tuple fields, local HTTP paths, exact RTSP
paths, BLE characteristic roles, DWARF 3 profile negotiation, direct-photo
abort and the 7,200-second time warning. See [unknowns.md](unknowns.md).

## 18. Recommended next captures

[unknowns.md](unknowns.md) specifies device/firmware, application action,
transport and distinguishing evidence for each unknown. The highest-value next
capture is one controlled Mini dark-calibration set through the official app,
including 11045, 15290/15291 and the resulting album/file transaction.
