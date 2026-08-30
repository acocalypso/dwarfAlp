# Unresolved questions

| Question | Current evidence/hypothesis | Confidence | Next safe step |
|---|---|---|---|
| What bootloader/base distribution is used? | update bundle lacks boot artifacts/rootfs | UNKNOWN | obtain authorized full image or support bundle |
| What are the complete partitions and A/B/rollback rules? | only media partition p10 appears in script | UNKNOWN | inspect full partition table read-only |
| What are the DT hardware connections? | sensor modules and GPIO scripts only | UNKNOWN | obtain/decompile DTB |
| Is the outer firmware bundle cryptographically authenticated? | `bilbo_upgrade` verifies per-file MD5 values from `update.json`; the RSA verifier in `bilbo` serves activation messages, not the observed update path | UNKNOWN | trace the upload/staging call graph in `bilbo`; do not bypass integrity checks |
| What are the SSH authentication and service-user policies? | only startup call supplied | UNKNOWN | obtain non-secret base configuration |
| What maps UART1/UART3 to axes/controllers? | both configured, motor API present | LOW | board/DT evidence or passive serial trace |
| What CPU/container protects `motor.bin`? | entropy 7.9767, no reliable header/strings | UNKNOWN | vendor documentation or updater decompilation |
| What physical wheel position corresponds to each filter enum? | APK proves VIS=0, Astro=1, Duo-Band=2, Dark=3; normal choices are model-specific, while calibration explicitly sends Dark=3 | UNKNOWN physical positions | correlate motor/filter notifications with opt-in selections on each model |
| What is the live `device.db` schema? | ORM names only; DB absent | UNKNOWN | inspect a sanitized authorized copy read-only |
| What are the exact terminal-state values for every calibration/tracking firmware release? | state machines and notification schemas are recovered, but success/failure timing differs by firmware | MEDIUM | correlate sanitized passive captures with device/app logs by firmware version |
| Which device-HTTP routes are available on every model? | firmware and APK expose overlapping route sets, but this update is Mini-specific | MEDIUM | perform read-only route probes on each authorized model and version |
