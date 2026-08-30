# Filesystem and persistent data

The update bundle alone cannot reconstruct the root filesystem. An authorized
raw acquisition of a live Mini on 2026-08-30/31 recovered p1-p9, including the
complete 2 GiB rootfs and the OEM/userdata filesystems. Private images and
extracted state remain outside Git. The 56.9 GB user-media partition was
intentionally excluded. See [18-live-image-analysis.md](18-live-image-analysis.md).

```text
/
├── etc/init.d/S50usbdevice       supplied boot hook
├── userdata/                    application/configuration area
│   ├── nginx/www/               nginx document root
│   └── astro/                   astrometry indexes/data (referenced)
├── usrdata/astro/               tele/wide capture paths (binary strings)
├── DWARF_mini/                  mounted exFAT media volume
├── tmp/update.json              staged update metadata
├── var/run/wpa_supplicant/      Wi-Fi control socket
└── restore/device.db            database restore clue
```

The live userdata filesystem contains `/userdata/astro`; `/usrdata/astro/...`
remains a binary string and is not a mounted live path. It is most likely a
historical path or typo, but its original call-site purpose remains unresolved.
**PARTIAL**

The live partition map is an eMMC with ten named partitions: `env`, `idblock`,
`uboot`, `boot`, `misc`, `recovery`, `rootfs` (2 GiB), `oem` (1 GiB),
`userdata` (2 GiB), and the remaining media area mounted as `/DWARF_mini`.
The system has no observed A/B rootfs pair. This resolves the physical layout,
but not recovery or rollback policy. **VERIFIED on Mini 1.1.3.2 binaries**

The live WCDB file is `/userdata/data/device.db`. The acquired database and its
WAL/SHM pass SQLite `PRAGMA quick_check`. Schema and non-secret parameter rows confirm tables
for `astro_info`, `astro_fits_info`, `astro_multi_stack_info`, mosaics and
subviews, `cali_frame_info`, picture/video/burst/panorama albums, camera/ISP
parameters, stack settings, and shooting schedules/tasks. Important astronomy
columns include exposure, gain, filter, target, RA/Dec, requested/taken/stacked
counts, FITS path/name/MD5/size, stack state/code, temperature, location,
equatorial mode, and rotation. Published analysis excludes private media paths,
target history, schedules, location values, credentials, and user media.
**VERIFIED**
