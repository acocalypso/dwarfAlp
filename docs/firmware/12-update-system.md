# Firmware update system

The bundle uses JSON manifests containing installation targets and execution
flags. `bilbo` supplies HTTP upload/update handlers and stages `/tmp/update.json`;
strings show archive extraction into `/tmp`. `bilbo_upgrade` performs version
comparison, manifest processing, MD5 checks, copying/moving/deleting, and the
actual installation. **HIGH**

A Ghidra decompilation of `bilbo_upgrade` shows `processUpdateJson`,
`upgradeFirmware`, `compareFileMd5`, and MD5 routines. In that replacement-file
updater, each package described by the outer `/oem/update.json` is checked using
MD5; no RSA/EVP verification call was found in that binary. **VERIFIED for the
inner updater; UNKNOWN whether another stage authenticates the complete bundle**

The main `bilbo` service does contain a SHA-256 plus `RSA_verify` routine, but
its recovered call sites process activation-service messages such as
`getActivateCode`, `activateStatusNotify`, and `resetActivate`. It is therefore
not evidence of update signing. The earlier association between this routine
and the updater was incorrect. **VERIFIED activation scope for the observed
call sites; UNKNOWN update authentication**

The update ZIP contains no complete partition image. The later live acquisition
does contain signed Rockchip FIT U-Boot, boot, and recovery partitions and shows
no A/B rootfs pair. FIT metadata includes SHA-256/RSA-2048 signatures and
rollback-index fields, but boot-time enforcement and recovery rollback policy
remain unresolved.

Live, testing clarified the differential-update result:

- a minimal `config/update.json` plus `config/run.sh` package is accepted and
  installs `/userdata/run.sh`;
- successful metadata `oldVersion=1.1.3.2`, `newVersion=1.1.3.6` advanced
  `/userdata/config/factory/firmware_version.json` to 1.1.3.6;
- the `bilbo` binary and `bilbo_upgrade` hashes still exactly match the supplied
  1.1.3.2 bundle, and `/getDefaultParamsConfig` still reports 1.1.3.2;
- repeating the request with stale `oldVersion=1.1.3.2` returns code `-10`, and
  the device log identifies it as `upgradeSoftware: version error` before
  extraction.

The factory/update version is consequently an installer ledger, not proof that
the application binaries were replaced. Missing optional package groups such
as `iq`, `bin`, `libs`, `mcu`, and `model` are logged during a minimal patch but
do not prevent the present `config` group from being processed. **VERIFIED**

The raw userdata/OEM snapshots independently confirm this result: live `bilbo`,
`bilbo_upgrade`, astrometry tools, MCU payloads, and models are byte-identical to
the 1.1.3.2 update bundle, while only the factory version ledger differs. The
diagnostic ZIPs and appended Telnet startup line are explicitly classified as
user-generated test artifacts rather than manufacturer firmware evidence.

Update, reset, MCU flashing, and factory endpoints are intentionally not wired
into DwarfAlp. This analysis does not describe bypassing integrity or signatures.
