# Investigation journal

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

- Ghidra call-graph/decompilation of port binding and signature scope: useful but
  not required for the verified integration and not installed without approval.
- Dynamic/QEMU analysis: unjustified for this package at present because exact
  descriptors and configs answered the high-value safe questions; dependencies
  and side effects are extensive.
