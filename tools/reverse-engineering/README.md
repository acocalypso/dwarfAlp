# Reproducible decompilation environment

This container performs static interoperability research on locally supplied
DWARFLAB APK bundles and authorized DWARF firmware. It never executes an APK or
firmware binary. Original artifacts are mounted read-only and generated output
is written to the ignored `build/reverse-engineering/` directory.

## Included tools

| Tool | Version | Purpose |
|---|---:|---|
| JADX | 1.5.6 | DEX/Kotlin/Java decompilation across APKS splits |
| apktool | 3.0.3 | Android resources, manifest, and smali decoding |
| Ghidra | 12.1.3 | ARM/ARM64 ELF analysis and C-like decompilation |
| OpenJDK | 21 | JADX, apktool, and Ghidra runtime |
| binutils, `file`, `dtc`, SQLite, protobuf compiler, `rg`, `jq` | Ubuntu 24.04 packages | Binary and data inspection |

Downloaded tool archives are pinned by SHA-256 in the Dockerfile. The Ubuntu
base image is pinned by manifest digest.

## Build and verify

Run these commands from the repository root:

```powershell
New-Item -ItemType Directory -Force build/reverse-engineering | Out-Null
docker compose -f tools/reverse-engineering/compose.yaml build
docker compose -f tools/reverse-engineering/compose.yaml run --rm analyzer versions
```

The build requires network access to download packages and the pinned tools.
Runtime analysis has `network_mode: none`, drops all Linux capabilities, uses a
read-only container filesystem, and applies `no-new-privileges`.

## APK decompilation

The default command processes `apk/DWARFLAB_3.4.1_apkcube.apks`:

```powershell
docker compose -f tools/reverse-engineering/compose.yaml run --rm analyzer apk
```

Results include JADX sources, apktool resources/smali, extracted split APKs,
and native libraries below `build/reverse-engineering/apk/`.

## Firmware extraction and native decompilation

Extract and inventory the update bundle:

```powershell
docker compose -f tools/reverse-engineering/compose.yaml run --rm analyzer firmware
```

Then decompile a chosen ELF from the existing ignored extraction tree:

```powershell
docker compose -f tools/reverse-engineering/compose.yaml run --rm analyzer `
  decompile /input/extracted/dwarf_mini_v1.1.3.2/bin/bilbo bilbo
```

For a faster first pass, select functions that reference protocol, networking,
capture, filter, database, and update keywords, plus their direct callers:

```powershell
docker compose -f tools/reverse-engineering/compose.yaml run --rm analyzer `
  triage /input/extracted/dwarf_mini_v1.1.3.2/bin/bilbo bilbo-triage
```

The triage mode writes `string-xrefs.tsv`, `functions.tsv`, and `targeted.c`.
Use it before a full export; a full export of the large `bilbo` binary can take
hours because optimized library and generated protobuf functions are included.

Export a whole-program derived inventory (functions, imports, memory blocks,
strings and their callers, and function call edges) without decompiled bodies:

```powershell
docker compose -f tools/reverse-engineering/compose.yaml run --rm analyzer `
  inventory /input/extracted/dwarf_mini_v1.1.3.2/bin/bilbo bilbo-inventory
```

Ghidra writes a combined `decompiled.c`, `functions.tsv`, and its analysis log
below `build/reverse-engineering/ghidra/<name>/`. Existing outputs are never
silently overwritten; move or remove a specific output directory before a
deliberate rerun.

When an authorized filesystem image supplies the target's shared libraries,
pass Ghidra's semicolon-separated library search paths as the final argument.
The wrapper enables `ElfLoader` dependency loading to depth two and links the
direct and transitive project libraries instead of leaving their external
symbols unresolved:

```powershell
docker compose -f tools/reverse-engineering/compose.yaml run --rm analyzer `
  inventory /input/extracted/live-mini/bin/bilbo_s bilbo-s 1800 `
  '/input/extracted/live-mini/userdata/lib;/input/extracted/live-mini/oem/usr/lib;/input/extracted/live-mini/rootfs/lib'
```

Runtime TLS and `R_ARM_COPY` relocations can still produce loader warnings;
those are different from missing dependency files and do not mean that the
original ELF is damaged.

Use `targeted` with comma-separated function addresses to decompile selected
handlers and their direct callers and callees without exporting the complete
program:

```powershell
docker compose -f tools/reverse-engineering/compose.yaml run --rm analyzer `
  targeted /input/extracted/live-mini/bin/bilbo_s `
  '0012cde4,0012dbc4,00122558' bilbo-s-astro 1800 `
  '/input/extracted/live-mini/userdata/lib;/input/extracted/live-mini/oem/usr/lib;/input/extracted/live-mini/rootfs/lib'
```

## Research boundaries

- Use only artifacts you are authorized to inspect.
- Do not publish vendor decompiler output or original binaries; publish derived
  interoperability facts, hashes, and minimal evidence references.
- Do not use this environment to bypass signatures, authentication, safety
  limits, or access controls.
- Treat all conclusions as hypotheses until corroborated by code paths, passive
  captures, or opt-in hardware tests.
