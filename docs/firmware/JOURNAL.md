# Investigation journal

## 2026-08-30

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
