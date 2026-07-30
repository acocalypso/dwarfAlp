# DWARFLAB 3.4.1 interoperability analysis

Analysis date: 2026-07-30
Package: `com.convergence.dwarflab`
Version: 3.4.1 (677)
Base APK SHA-256:
`1E4F676A35EBE6F9D8CB7B3FB4720346C45C41FC41B7E7807151B0080C5DE294`
Bundle SHA-256:
`31A7260A66EA4CCD72C3AAD37D5B7F4F345A734D5BC636040B6B12B9951BE7FC`

This directory records interoperability findings from local static analysis,
authorized packet captures, and opt-in DWARF Mini testing. Decompiled code is
not redistributed. Evidence locations refer to the ignored local JADX tree
`build/apk-audit-3.4.1/decompiled/sources`.

## Baseline

| Item | Path or revision | Status | Notes |
|---|---|---|---|
| Main repository | `729cc1f8db52d6d4925c5b37d4127cd3efd27774` | clean before analysis | branch `main` |
| API research repository | `dwarfii_api@9644393502269b88bd11f0636f1972a7608dd92a` | clean before analysis | branch `develop`, own fork is `origin` |
| APK bundle | `apk/DWARFLAB_3.4.1_apkcube.apks` | verified | 33 APK entries |
| Base APK | `build/apk-audit-3.4.1/base.apk` | verified | 7 DEX files, 3,659 ZIP entries |
| JADX sources | `build/apk-audit-3.4.1/decompiled/sources` | available | 24,532 Java files |
| Decoded manifest | `build/apk-audit-3.4.1/resources-decoded/resources/AndroidManifest.xml` | available | 51 activities, 19 services, 9 receivers, 11 providers |
| Native code | arm64 split | inventoried | 15 libraries; media, astronomy and map rendering |
| Captures | `dwarfii_api/tools/v3-probe/pcaps` | available | Mini WebSocket and media captures |
| Baseline tests | repository | passed | 143 passed, 1 skipped |
| Baseline Ruff | repository | passed | `uv run ruff check .` |
| Baseline protobuf check | repository | failed | ignored generated bindings were stale |

## Tools

| Tool | Version/status |
|---|---|
| JADX | 1.5.5 |
| aapt / apksigner | Android build-tools 36.0.0 |
| Java | 17.0.12 |
| Python | 3.12.10 |
| uv | 0.9.26 |
| Git | 2.52.0 |
| apktool / apkanalyzer / tshark / protoc CLI | not present on PATH |

The APK is signed with a self-signed RSA-2048 certificate whose SHA-256 is
`9d3ae65083d44783019aecd4035c84c41d36c8a1deeea51ffbe6f672933bc916`.
APK signature schemes v1, v2 and v3 and a source stamp verify. The source stamp
contains Unix timestamp 1785314141 (2026-07-29 08:35:41 UTC); this is a signing
timestamp, not proof of the application source-build time.

## Outputs

- [Application architecture](app-architecture.md)
- [WebSocket protocol](websocket-protocol.md)
- [Other transports](transports.md)
- [API report](api-inventory.md)
- [Machine-readable inventory](api-inventory.json)
- [Capture workflows](capture-workflows.md)
- [Compatibility and gap analysis](model-compatibility.md)
- [Evidence index](evidence-index.md)
- [Unknowns and capture plan](unknowns.md)
- [Final investigation report](final-report.md)

Confidence labels are literal: confirmed in app code and hardware traffic,
confirmed in app code, confirmed in packet capture, confirmed on hardware,
confirmed in official documentation, strongly inferred, tentative, or unknown.
