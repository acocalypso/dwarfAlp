# DWARF Mini firmware 1.1.3.2 analysis

This is an unofficial, evidence-led static analysis of
`dwarf_mini_upgrade_firmware_v1.1.3.2.zip`. The bundle was treated as untrusted:
no ARM program was executed, no update was installed, and no command was sent to a
physical DWARF.

The package is an **application/update bundle**, not a complete flash dump. It
contains the main `bilbo` service, its updater, configuration, camera tuning,
sensor modules, MCU payloads, and an RKNN model. It does not contain a bootloader,
kernel image, DTB, or complete root filesystem.

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
| Factory and destructive update operations exist but are not suitable for DwarfAlp exposure | VERIFIED |

Start with the [firmware overview](01-firmware-overview.md), then use the
[source index](SOURCE_INDEX.md) to trace claims to evidence. Exact recovered
protobuf metadata is retained in
`firmware-analysis/metadata/bilbo-protos.json`; the generated human reference is
[07-device-protocol.md](07-device-protocol.md).

Confidence labels used throughout:

- **VERIFIED**: directly demonstrated by a bundled file, schema, or binary metadata.
- **HIGH**: multiple independent clues support the conclusion.
- **MEDIUM**: plausible interpretation with incomplete proof.
- **LOW**: weak clue retained for investigation.
- **UNKNOWN**: the necessary evidence is absent.
