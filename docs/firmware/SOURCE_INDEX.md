# Source and evidence index

| Finding | Primary evidence | Location/offset | Confidence |
|---|---|---|---|
| Original bundle identity | SHA-256 inventory | `firmware/...1.1.3.2.zip` | VERIFIED |
| ARM/uClibc ABI | ELF headers/interpreters | extracted `bin/*`, `libs/*` | VERIFIED |
| Linux 5.10.160 | kernel module vermagic | `libs/imx662_12bit.ko`, `os02k10_12bit.ko` | VERIFIED |
| RV1106 platform | paths and Rockchip imports | `bin/bilbo` | HIGH |
| Startup/service sequence | shell implementation | `bin/run.sh`, `bin/S50usbdevice` | VERIFIED |
| USB topology | configfs shell implementation | `bin/S50usbdevice` | VERIFIED |
| nginx/FTP exposure | supplied configs | `config/nginx.conf`, `vsftpd.conf` | VERIFIED |
| Camera sensors/modes | modules and IQ JSON | `libs/*.ko`, `iq/*` | VERIFIED |
| Shooting modes/settings | YAML configuration | `config/default_params_configs.yaml` | VERIFIED |
| Exact message schemas | serialized `FileDescriptorProto` | `bin/bilbo` offsets in `bilbo-protos.json` | VERIFIED |
| Device state schema | `task_center.proto` descriptor | `bin/bilbo` near `0x852430` | VERIFIED |
| Astro schema | `astro.proto` descriptor | `bin/bilbo` near `0x8468b4` | VERIFIED |
| Factory surface | `factoryTest.proto` descriptor | `bin/bilbo` near `0x84b1cc` | VERIFIED |
| HTTP routes | handler/path strings | `bin/bilbo` | VERIFIED |
| FITS-list HTTP method | Ghidra route-registration call graph | `bin/bilbo` at function `0x003a54d0` | VERIFIED (`POST`) |
| Service bind ports | Ghidra constructors plus live socket ownership | `bin/bilbo`: 9900, 8082, 8085, 8092, 554; loopback 3893 | VERIFIED |
| Astronomy pipeline | linked libraries, tools, symbols/strings | `bin/bilbo`, `bin/astrometry.cfg`, WCS tools, model | HIGH |
| Update system | symbols/imports/manifests | `bin/bilbo`, `bilbo_upgrade`, `*/update.json` | HIGH |
| Inner updater integrity | Ghidra call graph/decompilation | `bin/bilbo_upgrade`: `processUpdateJson`, `compareFileMd5` | VERIFIED |
| RSA verification scope | Ghidra function/caller decompilation | `bin/bilbo`: SHA-256/RSA activation-message handlers | VERIFIED for observed callers; not update evidence |
| WCDB persistence | ORM RTTI/symbols and paths | `bin/bilbo` | HIGH |
| MCU payload classification | entropy, initial bytes, printable strings | `mcu/motor.bin`, `mcu/rgb.bin` | VERIFIED/HIGH |
| Whole-program structure | Ghidra function/import/string/call/memory inventory | ignored `build/reverse-engineering/ghidra/bilbo-inventory/` | VERIFIED derived inventory |
| Runtime lifecycle | initialization symbols, call edges, configs, imports | `bin/bilbo`, `bin/run.sh`, `config/*` | HIGH |
| Live Mini hardware/storage | authorized read-only `/proc`, mounts, and device tree | RV1106G EVB1 V10; ten eMMC partitions; IMX662@0x1a; OS02K10@0x21 | VERIFIED |
| Live persistence schema | authorized schema-only `strings` inspection | `/userdata/data/device.db`; record values excluded | VERIFIED |
| Differential update code `-10` | device Bilbo log | `upgradeSoftware: version error` with stale `oldVersion` | VERIFIED |

Machine-readable sources:

- `firmware-analysis/metadata/inventory.json`
- `firmware-analysis/metadata/bilbo-protos.json`
- `firmware-analysis/metadata/bilbo-protos.pb`
- [17-bilbo-internals.md](17-bilbo-internals.md)

Generated JADX/Ghidra work products remain ignored under
`build/reverse-engineering/`. The reproducible, pinned container and export
scripts are maintained in `tools/reverse-engineering/`.

The metadata identifies the analyzed binary by SHA-256 and records each
descriptor's byte offset and hash, allowing exact reproduction without trusting
the prose.
