# Unresolved questions

| Question | Current evidence/hypothesis | Confidence | Next safe step |
|---|---|---|---|
| What bootloader/base distribution is used? | live system is BusyBox/SysV-style on Linux 5.10.160; bootloader image remains unavailable | PARTIAL | inspect authorized boot metadata or image without modifying flash |
| What are the recovery and rollback rules? | live map has ten named eMMC partitions and no observed A/B rootfs pair | PARTIAL | statically inspect authorized recovery/boot images |
| What are the remaining DT hardware connections? | live DT resolves the RV1106G board and both sensor I2C attachments | PARTIAL | map CSI lanes, PWM/GPIO roles, and motor UARTs from the live DT |
| Is the outer firmware bundle cryptographically authenticated? | `bilbo_upgrade` verifies per-file MD5 values from `update.json`; the RSA verifier in `bilbo` serves activation messages, not the observed update path | UNKNOWN | trace the upload/staging call graph in `bilbo`; do not bypass integrity checks |
| What are the SSH authentication and service-user policies? | only startup call supplied | UNKNOWN | obtain non-secret base configuration |
| What maps UART1/UART3 to axes/controllers? | both configured, motor API present | LOW | board/DT evidence or passive serial trace |
| What CPU/container protects `motor.bin`? | entropy 7.9767, no reliable header/strings | UNKNOWN | vendor documentation or updater decompilation |
| What physical wheel position corresponds to each filter enum? | APK proves VIS=0, Astro=1, Duo-Band=2, Dark=3; normal choices are model-specific, while calibration explicitly sends Dark=3 | UNKNOWN physical positions | correlate motor/filter notifications with opt-in selections on each model |
| What are the exact terminal-state values for every calibration/tracking firmware release? | state machines and notification schemas are recovered, but success/failure timing differs by firmware | MEDIUM | correlate sanitized passive captures with device/app logs by firmware version |
| Which device-HTTP routes are available on every model? | firmware and APK expose overlapping route sets, but this update is Mini-specific | MEDIUM | perform read-only route probes on each authorized model and version |
| What uses Bilbo's loopback TCP port 3893? | live socket ownership proves Bilbo listens only on 127.0.0.1 | UNKNOWN | trace the constructor/caller and observe local connections passively |
