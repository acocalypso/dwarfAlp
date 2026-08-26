# Filesystem and persistent data

A complete root filesystem cannot be reconstructed from this update bundle.
Only installation targets and runtime paths referenced by manifests, scripts,
configuration, and binaries can be mapped.

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

Persistent records use WCDB/SQLite abstractions. Identifiable entities include
astronomy captures, FITS, multi-stack and mosaic records, calibration frames,
burst/panorama/picture/video records, shooting modes, schedules, tasks,
settings, and events. The actual `device.db` is absent, so table columns and
live user data were not inspected. **VERIFIED / schema details UNKNOWN**
