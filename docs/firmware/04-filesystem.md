# Filesystem and persistent data

A complete root filesystem cannot be reconstructed from the update bundle
alone. A read-only inspection of a live Mini on
2026-08-30 confirmed the runtime mounts and persistent application paths below.

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

The firmware contains both `/userdata/astro` and `/usrdata/astro/...` strings.
They may refer to different areas or one may be a historical typo; the bundle
does not resolve the discrepancy. **UNKNOWN**

The live partition map is an eMMC with ten named partitions: `env`, `idblock`,
`uboot`, `boot`, `misc`, `recovery`, `rootfs` (2 GiB), `oem` (1 GiB),
`userdata` (2 GiB), and the remaining media area mounted as `/DWARF_mini`.
The system has no observed A/B rootfs pair. This resolves the physical layout,
but not recovery or rollback policy. **VERIFIED on Mini 1.1.3.2 binaries**

The live WCDB file is `/userdata/data/device.db`. Schema strings confirm tables
for `astro_info`, `astro_fits_info`, `astro_multi_stack_info`, mosaics and
subviews, `cali_frame_info`, picture/video/burst/panorama albums, camera/ISP
parameters, stack settings, and shooting schedules/tasks. Important astronomy
columns include exposure, gain, filter, target, RA/Dec, requested/taken/stacked
counts, FITS path/name/MD5/size, stack state/code, temperature, location,
equatorial mode, and rotation. Only schema text was inspected; record values
and user media were not collected. **VERIFIED**
