# Firmware overview

## Evidence baseline

| Original artifact | Size | Container | SHA-256 | Confidence |
|---|---:|---|---|---|
| `firmware/dwarf_mini_upgrade_firmware_v1.1.3.2.zip` | 13,076,330 bytes | ZIP update bundle | `fe858626c2b13ef007983fa0171b49b4bb87e05fbd78fdf62fd9693c0809504d` | VERIFIED |

The original artifact remains untouched. Extraction was performed with path
traversal checks into the ignored `firmware-analysis/extracted/` tree. The
bundle contains 43 files. See
`firmware-analysis/metadata/inventory.md` for every extracted file, size, file
classification, SHA-256, and Shannon entropy.

No SquashFS, UBI/UBIFS, JFFS2, ext filesystem, CramFS, cpio/initramfs, FIT,
uImage, Android sparse image, MBR, or GPT container was found. This is a
cross-checked ZIP of replacement files and manifests, not a full firmware
image. **VERIFIED**

## Contents

```text
update bundle
├── bin/       bilbo, updater, nginx, scripts, astrometry tools
├── config/    service, Wi-Fi, camera/default and factory configuration
├── iq/        IMX662 and OS02K10 image-quality tuning
├── libs/      shared libraries and camera kernel modules
├── mcu/       opaque motor and RGB-controller update payloads
└── model/     sky-segmentation RKNN model
```

The Broadcom file `fw_bcm43456c5_ag.bin` is classified by `file` as an OpenPGP
key. Its vendor filename, colocated AP6256 NVRAM, and update role contradict
that signature guess; it is treated as Wi-Fi firmware, with the tool result
recorded as a false positive. **HIGH**

## Reproduction

```powershell
pwsh tools/firmware/Extract-Firmware.ps1 `
  -Archive firmware/dwarf_mini_upgrade_firmware_v1.1.3.2.zip `
  -Destination firmware-analysis/extracted/dwarf_mini_v1.1.3.2
uv run python tools/firmware/inventory_firmware.py `
  firmware-analysis/extracted/dwarf_mini_v1.1.3.2 `
  --json firmware-analysis/metadata/inventory.json `
  --markdown firmware-analysis/metadata/inventory.md
uv run python tools/firmware/extract_protobuf_descriptors.py `
  firmware-analysis/extracted/dwarf_mini_v1.1.3.2/bin/bilbo `
  --source-label dwarf_mini_v1.1.3.2/bin/bilbo `
  --descriptor-set firmware-analysis/metadata/bilbo-protos.pb `
  --json firmware-analysis/metadata/bilbo-protos.json
```

ELF scanning is available through `tools/firmware/scan_elfs.sh` in WSL. Exact
embedded protobuf descriptors can be recovered with
`tools/firmware/extract_protobuf_descriptors.py`.
