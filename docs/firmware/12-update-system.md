# Firmware update system

The bundle uses JSON manifests containing installation targets and execution
flags. `bilbo` supplies HTTP upload/update handlers and stages `/tmp/update.json`;
strings show archive extraction into `/tmp`. `bilbo_upgrade` performs version
comparison, manifest processing, MD5 checks, copying/moving/deleting, and the
actual installation. **HIGH**

OpenSSL imports in `bilbo` include RSA key loading, RSA sign/verify, SHA-256,
SHA-1, AES, and EVP functions, and a `verifySignature` clue. This supports an
authenticated-update design, but static evidence has not yet proven exactly
which bytes are signed or the full trust-chain/control flow. **HIGH that
signature verification exists; UNKNOWN signed scope**

No complete partition image, A/B metadata, rollback implementation, bootloader,
or recovery image is present. A/B strategy and rollback behavior are UNKNOWN.

Update, reset, MCU flashing, and factory endpoints are intentionally not wired
into DwarfAlp. This analysis does not describe bypassing integrity or signatures.
