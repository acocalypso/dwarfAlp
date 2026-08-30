# DWARF Mini firmware 1.1.3.2 analysis

This is an unofficial, evidence-led analysis of
`dwarf_mini_upgrade_firmware_v1.1.3.2.zip`, the decompiled DWARFLAB app, and an
authorized read-only image of a live DWARF Mini. Vendor ARM programs were never
executed on the analysis workstation. Private device images, credentials,
database records, logs, and diagnostic artifacts remain local and outside Git.

The package is an **application/update bundle**, not a complete flash dump. It
contains the main `bilbo` service, its updater, configuration, camera tuning,
sensor modules, MCU payloads, and an RKNN model. It does not contain a bootloader,
kernel image, DTB, or complete root filesystem; those surfaces are documented
separately from the authorized live partition acquisition.

## Headline findings

| Finding | Confidence |
|---|---|
| ARMv7-A, little-endian, hard-float, uClibc userspace | VERIFIED |
| Rockchip RV1106 application platform | HIGH |
| Linux 5.10.160 camera-module ABI | VERIFIED |
| `bilbo` is the central camera, motion, astronomy, HTTP, WebSocket, and persistence service | HIGH |
| The bundle embeds 16 complete protobuf file descriptors | VERIFIED |
| IMX662 and OS02K10 12-bit camera drivers and IQ data are supplied | VERIFIED |
| astrometry.net/WCS, OpenCV, RKNN sky segmentation, FITS, FFmpeg, and Rockchip media libraries participate in imaging | VERIFIED |
| Startup enables RNDIS/mass storage, FTP, SSH, nginx, BLE, `bilbo`, and the updater | VERIFIED |
| Signed Rockchip FIT boot, recovery, and U-Boot images use SHA-256/RSA-2048 metadata | VERIFIED live image |
| Live `bilbo` and core payloads remain byte-identical to Mini 1.1.3.2 despite the 1.1.3.6 installer ledger | VERIFIED |
| Factory and destructive update operations exist but are not suitable for DwarfAlp exposure | VERIFIED |

Start with the [firmware overview](01-firmware-overview.md), then use the
[source index](SOURCE_INDEX.md) to trace claims to evidence. Exact recovered
protobuf metadata is retained in
`firmware-analysis/metadata/bilbo-protos.json`; the generated human reference is
[07-device-protocol.md](07-device-protocol.md).

For the consolidated native runtime model, decompilation coverage, capture
pipeline, and service ownership, see [17-bilbo-internals.md](17-bilbo-internals.md).
For acquisition boundaries, raw partition results, boot-chain evidence,
database layers, and runtime-log findings, see
[18-live-image-analysis.md](18-live-image-analysis.md).

Confidence labels used throughout:

- **VERIFIED**: directly demonstrated by a bundled file, schema, or binary metadata.
- **HIGH**: multiple independent clues support the conclusion.
- **MEDIUM**: plausible interpretation with incomplete proof.
- **LOW**: weak clue retained for investigation.
- **UNKNOWN**: the necessary evidence is absent.
