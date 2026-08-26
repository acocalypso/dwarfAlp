# Unresolved questions

| Question | Current evidence/hypothesis | Confidence | Next safe step |
|---|---|---|---|
| What bootloader/base distribution is used? | update bundle lacks boot artifacts/rootfs | UNKNOWN | obtain authorized full image or support bundle |
| What are the complete partitions and A/B/rollback rules? | only media partition p10 appears in script | UNKNOWN | inspect full partition table read-only |
| What are the DT hardware connections? | sensor modules and GPIO scripts only | UNKNOWN | obtain/decompile DTB |
| Which exact ports does this firmware bind for WebSocket/HTTP/JPEG/RTSP? | client/capture ports known; static bind constants unresolved | HIGH/MEDIUM | isolated Ghidra xrefs or passive socket inventory |
| Is `/album/astro/fitsList` DELETE or POST on 1.1.3.2? | firmware string context conflicts with newer APK | UNKNOWN | passive HTTP capture or read-only request validation |
| Which bytes are covered by update signatures? | RSA verify and manifests present | UNKNOWN | decompile verification call graph, no bypass/testing |
| What are the SSH authentication and service-user policies? | only startup call supplied | UNKNOWN | obtain non-secret base configuration |
| What maps UART1/UART3 to axes/controllers? | both configured, motor API present | LOW | board/DT evidence or passive serial trace |
| What CPU/container protects `motor.bin`? | entropy 7.9767, no reliable header/strings | UNKNOWN | vendor documentation or updater decompilation |
| What is the exact filter enum/physical position mapping including Dark? | two-value list, three-name comment, hidden dark behavior | UNKNOWN | capture commands/notifications for each app selection |
| How do exposure indexes 0–168 map to seconds? | parameter definition lacks table | UNKNOWN | recover lookup via decompilation or passive paired captures |
| What is the live `device.db` schema? | ORM names only; DB absent | UNKNOWN | inspect a sanitized authorized copy read-only |
