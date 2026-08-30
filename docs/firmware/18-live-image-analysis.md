# Live Mini image analysis

## Acquisition boundary

An authorized, read-only acquisition of a running DWARF Mini was completed on
2026-08-30/31 through the temporary diagnostic shell. Raw partition bytes were
streamed over a separate TCP connection; Telnet was used only to start `dd`.
No partition was written, remounted, frozen, or stopped during acquisition.

The original images, their manifest, and extracted private state are retained
locally outside Git. The media partition and its user captures were deliberately
excluded. Wi-Fi credentials, database record contents, logs containing personal
data, crash dumps, and the diagnostic updater payload are not published.

| Partition | Size | Acquisition result |
|---|---:|---|
| p1 `env` | 32 KiB | exact size; device/local MD5 matched |
| p2 `idblock` | 512 KiB | exact size; device/local MD5 matched |
| p3 `uboot` | 256 KiB | exact size; device/local MD5 matched |
| p4 `boot` | 32 MiB | exact size; device/local MD5 matched |
| p5 `misc` | 64 KiB | exact size; device/local MD5 matched |
| p6 `recovery` | 256 MiB | exact size; device/local MD5 matched |
| p7 `rootfs` | 2 GiB | exact size; device/local MD5 matched |
| p8 `oem` | 1 GiB | exact-sized live snapshot; source changed during verification |
| p9 `userdata` | 2 GiB | exact-sized live snapshot of a mounted writable filesystem |
| p10 media | 56,873,877,504 bytes | intentionally excluded; user media rather than system firmware |

The complete eMMC is 62,545,461,248 bytes. A whole-device acquisition is
technically possible, but the system partitions already contain the firmware
surfaces needed for this analysis. The p8/p9 captures are not forensic-atomic:
their filesystems were mounted and active. Journal recovery and `e2fsck` were
performed only on disposable working copies; the original images remain
unchanged. **VERIFIED**

## Boot chain and filesystems

The raw images resolve facts that the replacement-file update ZIP could not:

- p3 is a signed Rockchip FIT containing ATF, OP-TEE, U-Boot, an MCU/loadable,
  and a U-Boot DTB;
- p4 is a signed FIT containing the Linux kernel, board DTB, and resource;
- p6 is a signed recovery FIT containing kernel, DTB, resource, and ramdisk;
- FIT metadata names `rockchip,rv1106g-evb1-v10` and uses SHA-256/RSA-2048
  signatures;
- p7, p8, and p9 are ext4 filesystems mounted as `/`, `/oem`, and `/userdata`;
- p10 is exFAT and mounted as `/DWARF_mini`.

The booted system uses BusyBox init. `/etc/inittab` mounts the base filesystems
and executes `/etc/init.d/rcS`; `S21appinit` calls `/oem/usr/bin/RkLunch.sh`,
which loads OEM modules and finally executes `/userdata/run.sh`. That script
mounts media, initializes UART/GPIO/BLE, starts FTP, SSH and nginx, and launches
`bilbo` plus `bilbo_upgrade`. **VERIFIED from the live rootfs**

## Application identity

The live `/userdata/bin/bilbo` is 9,178,964 bytes and has SHA-256
`e7ae24fae358eda8ca301a231f000c23fae66df27571f0a92796c34bc54ad090`.
It is byte-identical to the binary in the analyzed 1.1.3.2 update ZIP. The live
`bilbo_upgrade`, astrometry tools, MCU payloads, and RKNN models are also
byte-identical to their 1.1.3.2 counterparts.

The factory update ledger reports 1.1.3.6 while `bilbo_config.json` and
`GET /getDefaultParamsConfig` report 1.1.3.2. This proves the diagnostic update
advanced the installer ledger without replacing the core application payload.
The small diagnostic ZIPs and the appended Telnet startup line found in the live
filesystems are user-generated test artifacts, not manufacturer firmware.
**VERIFIED**

## Persistent database

The acquired `/userdata/data/device.db` plus WAL/SHM files pass SQLite
`PRAGMA quick_check`. Inspection was limited to schema, row counts, and
non-secret operating parameters. Private media paths, target history, schedule
passwords, location values, and network credentials are excluded from the
published evidence.

The database contains the previously inferred album, FITS, calibration,
parameter, mosaic, and schedule tables. It also establishes three persisted
parameter layers:

- `param_type=0`: default/base values;
- `param_type=1`: saved normal settings;
- `param_type=2`: current/runtime values.

For the DSO tele camera, the captured current row held a 1-second exposure,
gain 60, filter 1, and stack count 1. This independently corroborates the V3
runtime-namespace behavior observed through parameter notification `15264`.
The database defines DSO as shooting mode 2 and uses synthetic parent mode
1000 (`CURRENT_MODE`) for runtime state. **VERIFIED on this Mini snapshot**

## Runtime-log findings

The retained Bilbo logs expose the internal one-click DSO goto sequence:

1. set one-click goto active and read `auto_calibration=1`;
2. construct `FocusWrapperAstro`;
3. compare user and factory infinity-focus positions;
4. reset or position the focus motor when required;
5. apply the autofocus exposure, gain, preview, and filter state;
6. run astronomy autofocus;
7. continue calibration, solve, and target goto through asynchronous state.

The logs resolve `-14511` as a focus/motor condition: the motor controller logs
`StepMotor 3 need reset`, after which `resetFocusMotor` returns `-14511`.
It is not a plate-solving or goto-limit response. The retry path performs one
additional reset attempt before the autofocus/goto workflow is ended.
**VERIFIED from retained runtime logs**

The live database and logs also show that a light frame can be written, dark
calibration applied, a thumbnail generated, and stacking continued as distinct
steps. A WebSocket start response therefore remains workflow admission rather
than proof that the final FITS or stack is ready.

## Remaining limitations

- p8/p9 should be reacquired from recovery or while unmounted if a
  forensic-consistent image becomes necessary.
- The complete media partition was not acquired.
- FIT signature verification policy and rollback-index enforcement still need
  call-graph and recovery analysis; the presence of signed FIT metadata alone
  does not prove every boot-time enforcement decision.
- The MiniDump is retained locally for symbolized crash analysis and is not
  published because it includes process memory and environment data.
