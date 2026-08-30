# Investigation journal

## 2026-08-31

- Proved an end-to-end raw acquisition path by streaming the 32 KiB environment
  partition over a dedicated TCP connection and matching the device/local MD5.
- Acquired p1-p9 from the authorized live Mini. Seven static/system partitions
  matched independent source hashes; OEM and userdata were retained as
  exact-sized live snapshots because their mounted filesystems changed during
  verification. The 56.9 GB user-media partition was intentionally excluded.
- Preserved original images and performed journal recovery/`e2fsck` only on
  disposable working copies. Extracted 4,021 rootfs, 301 OEM, and 188 userdata
  files locally; private state and images remain ignored and unpublished.
- Identified signed Rockchip FIT images: U-Boot includes ATF, OP-TEE, U-Boot,
  an MCU/loadable, and DTB; boot contains kernel/DTB/resource; recovery adds a
  ramdisk. FIT metadata uses SHA-256/RSA-2048 and names RV1106G EVB1 V10.
- Resolved the complete BusyBox startup chain from `/etc/inittab` through `rcS`,
  `S21appinit`, OEM `RkLunch.sh`, and `/userdata/run.sh`.
- Confirmed that live `bilbo`, `bilbo_upgrade`, astrometry tools, MCU payloads,
  and models are byte-identical to the 1.1.3.2 update bundle despite the factory
  ledger reporting 1.1.3.6. Classified the diagnostic ZIPs/Telnet hook as
  user-generated artifacts rather than manufacturer evidence.
- Opened the acquired WCDB/SQLite database read-only. It passes
  `PRAGMA quick_check`; published analysis is limited to schema, counts, and
  non-secret parameters. `param_type` 0/1/2 maps to default, saved, and current
  runtime layers, and mode 1000 is `CURRENT_MODE`.
- Traced the one-click DSO goto sequence in retained Bilbo logs. Error `-14511`
  follows `StepMotor 3 need reset` and is a focus-stepper reset failure, not a
  plate-solving response.

## 2026-08-30

- Used the diagnostic shell for a read-only live Mini
  inspection. Confirmed the RV1106G EVB1 V10 board, 185,916 KiB RAM, ten eMMC
  partitions, BusyBox/SysV startup, and live IMX662@0x1a plus OS02K10@0x21
  device-tree attachments. User media and database row values were excluded.
- Confirmed live process/socket ownership. Bilbo binds TCP/UDP 9900, HTTP 8082,
  raw-JPEG HTTP 8085, JPEG guide-stream TCP 8092, RTSP 554, and a loopback-only
  TCP 3893 service. SSH listens on 54227 rather than the default port 22.
- Inspected schema strings only from the live WCDB database, resolving the exact
  astronomy/FITS/stack/mosaic/calibration/settings/schedule table columns.
- Queried the live, read-only shooting catalogue. Mode 2 exposes Astro/Duo-Band
  on camera 0, tele exposures through 180 seconds, wide exposures through 30
  seconds, astronomy gain 40-240, stack count 1-999, mosaic count 1-249, and
  enabled auto-calibration. Supported modes require GET; parameter details use
  POST.
- Resolved update error `-10` as a version mismatch from the device log. The
  diagnostic patch advanced the installer ledger to 1.1.3.6, while Bilbo,
  `bilbo_upgrade`, and the embedded default configuration remain byte-identical
  to and report the supplied 1.1.3.2 payload.
- Added a network-disabled, read-only-at-runtime Docker analysis environment
  with pinned JADX 1.5.6, apktool 3.0.3, and Ghidra 12.1.3.
- Decompiled all APK splits. JADX recovered 24,530 Java files; 330 individual
  methods failed to decompile, with the remaining partial result preserved.
- Recovered the complete exposure-code lookup (0 through sparse value 174),
  device-specific ranges, device IDs, and logical filter enum from APK 3.4.1.
- Confirmed that normal live-stacking start serializes filter/force-start while
  the remaining capture parameters are set separately; calibration-frame start
  carries its parameters in the request itself.
- Decompiled all 935 functions in `bilbo_upgrade`. Its manifest workflow uses
  per-file MD5 comparison; no public-key verification call was found inside
  this updater. Authentication by an outer `bilbo` stage remains unresolved.
- Traced `bilbo`'s SHA-256/RSA verifier to cloud-activation message handlers,
  correcting the earlier unsupported assumption that the routine belonged to
  firmware-update verification.
- Completed targeted string-xref/caller triage of the much larger `bilbo`
  service: 353 high-value functions selected, 344 exported, and nine oversized
  functions timed out. The generated C-like output is intentionally ignored
  and not published.
- Resolved the 1.1.3.2 FITS-list ambiguity: `bilbo` registers
  `POST /album/astro/fitsList`; the neighboring delete route, not `fitsList`,
  uses DELETE.
- Confirmed `bilbo` bind constants for the WebSocket (9900), HTTP API (8082),
  JPEG service (8092), and RTSP service (554).
- Repaired the APK extractor for current JADX enum syntax and package-directory
  prefixes. The complete registry is 356 commands and 137 response codes; 14
  previously missed error states were added to the canonical protocol.
- Added a whole-program Ghidra inventory of functions, imports, memory blocks,
  strings/xrefs, and call edges, complementing the targeted and near-full
  decompilation attempts without publishing vendor method bodies.
- Consolidated `bilbo` startup, services, persistence, calibration/tracking,
  capture/FITS, and updater architecture in `17-bilbo-internals.md`.
- Moved DRACO-specific observations to an explicitly ignored local-only note.

## 2026-08-26

- Inspected repository and dirty state before edits; preserved the untracked
  `firmware/` artifact and avoided commits/pushes.
- Identified the sole original artifact, calculated its SHA-256, validated the
  ZIP, and extracted it with traversal checks into an ignored analysis tree.
- Generated a 43-file hash/type/entropy inventory.
- Used WSL Linux tools and an unprivileged extracted ARM binutils package for
  static ELF inspection; no firmware executable was run.
- Established ARMv7 hard-float/uClibc, Linux 5.10.160 module ABI, camera sensors,
  startup/services, USB behavior, media storage, and major libraries.
- Classified the motor payload as an opaque near-random container and the RGB
  payload as high-confidence 8051-compatible code from its initial instruction
  stream; neither was executed.
- Recovered 16 exact protobuf descriptors byte-for-byte from `bilbo`; retained a
  descriptor set and structured JSON with hashes/offsets.
- Compared the exact task-center schema to DwarfAlp and replaced the provisional
  command `16405` blob decoder with a typed, backward-compatible state subset.
- Added mocked state-decoding tests; focused test suite passed (75 tests).
- Context7 supplied current Ghidra headless documentation. Binwalk was not
  resolvable there; conventional file/archive tools were sufficient.

## Deferred

- Dynamic/QEMU analysis remains unjustified: exact descriptors, full static
  inventories, and targeted decompilation answer the high-value interoperability
  questions without executing a privileged hardware-control service.
