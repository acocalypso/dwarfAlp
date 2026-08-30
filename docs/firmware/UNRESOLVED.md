# Unresolved questions

| Question | Current evidence/hypothesis | Confidence | Next safe step |
|---|---|---|---|
| How is the signed boot chain enforced? | p3 is a Rockchip FIT with ATF/OP-TEE/U-Boot/MCU; p4 and p6 are signed boot/recovery FITs with SHA-256/RSA-2048 and rollback-index metadata | PARTIAL | trace U-Boot verification and rollback-index handling offline |
| What are the recovery and rollback rules? | recovery FIT and ramdisk are available locally; live map has no observed A/B rootfs pair | PARTIAL | extract recovery ramdisk and trace its update/restore scripts offline |
| What are the remaining DT hardware connections? | live DT resolves the RV1106G board and both sensor I2C attachments | PARTIAL | map CSI lanes, PWM/GPIO roles, and motor UARTs from the live DT |
| Is the outer firmware bundle cryptographically authenticated? | `bilbo_upgrade` verifies per-file MD5 values from `update.json`; the RSA verifier in `bilbo` serves activation messages, not the observed update path | UNKNOWN | trace the upload/staging call graph in `bilbo`; do not bypass integrity checks |
| What are the SSH authentication and service-user policies? | live rootfs supplies OpenSSH configuration and startup; private keys/password hashes remain excluded | PARTIAL | document non-secret directives and privilege boundaries only |
| What maps UART1/UART3 to axes/controllers? | both configured, motor API present | LOW | board/DT evidence or passive serial trace |
| What CPU/container protects `motor.bin`? | entropy 7.9767, no reliable header/strings | UNKNOWN | vendor documentation or updater decompilation |
| What physical wheel position corresponds to each filter enum? | APK proves VIS=0, Astro=1, Duo-Band=2, Dark=3; normal choices are model-specific, while calibration explicitly sends Dark=3 | UNKNOWN physical positions | correlate motor/filter notifications with opt-in selections on each model |
| What are the exact terminal-state values for every calibration/tracking firmware release? | state machines and notification schemas are recovered, but success/failure timing differs by firmware | MEDIUM | correlate sanitized passive captures with device/app logs by firmware version |
| Which device-HTTP routes are available on every model? | firmware and APK expose overlapping route sets, but this update is Mini-specific | MEDIUM | perform read-only route probes on each authorized model and version |
| What uses Bilbo's loopback TCP port 3893? | live socket ownership proves Bilbo listens only on 127.0.0.1 | UNKNOWN | trace the constructor/caller and observe local connections passively |
| Can p8/p9 be captured atomically? | live exact-sized images were acquired, but mounted filesystem activity changed OEM and may affect userdata | PARTIAL | reacquire from recovery or while unmounted if forensic consistency is required |
