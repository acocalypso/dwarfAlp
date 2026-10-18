# Official release acquisition — 2026-10-18

Downloaded the requested vendor update bundles for offline comparison. Both
match the API's byte count and MD5, pass ZIP CRC verification, and contain a
`config/factory/firmware_version.json` matching the requested version. These
checks establish download integrity, not signature verification or device
compatibility. No update was uploaded to a telescope.

| Model | Device ID | Version | Local file | Bytes | SHA-256 |
|---|---:|---|---|---:|---|
| DWARF 3 | 2 | 1.5.3.9 | `firmware/dwarf3_upgrade_firmware_v1.5.3.9.zip` | 90,538,283 | `f56c8792cb0c0a2f63fb9d45da8a95278adf6bd63cb24b77968d826b138dc8b0` |
| DWARF Mini | 4 | 1.1.4.4 | `firmware/dwarf_mini_upgrade_firmware_v1.1.4.4.zip` | 14,420,722 | `a6ea33a3332a4cb247db2003d13b55f0252dc4a6016985267734f6169c3416c9` |

The DWARF 3 ZIP has 140 entries; the Mini ZIP has 55 entries. Both are full
update archives (`updateFileType=0`, `fileDiff=null`), not complete flash images.
Original ZIPs remain local and ignored by Git under the repository's firmware
artifact policy. Public acquisition metadata and archive member inventories are
in `firmware-analysis/metadata/releases/`.

## Discovery and direct download links

The existing endpoint is already recorded in
`docs/apk-analysis/websocket-code-registry.md` and `api-inventory.json`.

Working DWARF 3 request:

<https://api-front.dwarflabapp.com/api-front/v1/version/firmware/up-version-ex?deviceId=2&firmwareVer=1.5.3.9&appOs=1&appVer=3.4.3>

Working Mini request:

<https://api-front.dwarflabapp.com/api-front/v1/version/firmware/up-version-ex?deviceId=4&firmwareVer=1.1.4.4&appOs=1&appVer=3.4.3>

API-returned download links:

- [DWARF 3 1.5.3.9 ZIP](https://global.dwarflabapp.com/dwarf-prod/system/fireware/version/2/dwarf3_upgrade_firmware_v1.5.3.9.zip)
- [DWARF Mini 1.1.4.4 ZIP](https://global.dwarflabapp.com/dwarf-prod/system/fireware/version/4/dwarf_mini_upgrade_firmware_v1.1.4.4.zip)

On this acquisition, `appOs=4` returned code `100101` (parameter error),
including with `appVer=3.4.3`. `appOs=1` with `appVer=3.4.3` succeeded. A
DWARF 3 query with `firmwareVer=0.0.0.0` returned the older 1.3.34 bridge
release. Queries with 1.5.3.8 and 1.5.3.9 returned 1.5.3.9. Therefore this API
is an upgrade selector and should not be treated as a simple maximum-version
lookup. The returned DWARF 3 metadata specifies minimum firmware 1.3.34;
both requested releases specify minimum Android/iOS app version 3.4.2.

Reproduce the download and verification from the repository root:

```powershell
python tools/firmware/download_release.py --device-id 2 --version 1.5.3.9
python tools/firmware/download_release.py --device-id 4 --version 1.1.4.4
```

The downloader requires an exact returned model/version, validates vendor size
and MD5 plus ZIP CRC, records SHA-256 and source metadata, and re-verifies an
existing destination instead of overwriting it.

## Newly supplied Android package

REA statically inspected the base APK from `apk/DWARFLAB_3.4.3_apkcube.apks`:

- Package: `com.convergence.dwarflab`; version **3.4.3**, build **750**.
- Minimum SDK 23; target SDK 36; 24,984 classes and 3,727 resources.
- APKS SHA-256: `d9d946b1bc2678063de544462a07ce0e029bc1f9ccca6ab38f1d09f49d8c894a`.
- Base APK SHA-256: `98f45d1f80e51923e812c5ec431e097e9f5b63ea29f95df52a0c05f7dd4cdd4f`.
- REA evidence: `ev_8a01bff6c358263b678aa9f26ed34ff9bad75c7b160658cc1310bc92b3e4c87a`.

The base APK was extracted into the ignored
`build/reverse-engineering/apk/DWARFLAB_3.4.3_apkcube/apk-set/` directory.
The package was not executed; signatures and split APKs were not verified.
Protocol differences from 3.4.1 have not yet been audited. Existing research
claims retain their original artifact/version scope.
