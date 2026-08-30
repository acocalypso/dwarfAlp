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

No complete partition image, A/B metadata, rollback implementation, bootloader,
or recovery image is present. A/B strategy and rollback behavior are UNKNOWN.

Update, reset, MCU flashing, and factory endpoints are intentionally not wired
into DwarfAlp. This analysis does not describe bypassing integrity or signatures.
