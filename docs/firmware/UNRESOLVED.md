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
