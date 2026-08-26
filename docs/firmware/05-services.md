# Vendor applications and services

| Component | Probable role | Key evidence | Confidence |
|---|---|---|---|
| `bilbo` | central device service | handlers, protobuf descriptors, camera/motor/astro symbols, network libraries | HIGH |
| `bilbo_upgrade` | local update installer | named update functions, manifests, MD5 and filesystem operations | VERIFIED |
| `nginx` | static media/web serving | supplied config and startup | VERIFIED |
| `vsftpd` | media-volume access | supplied config and startup | VERIFIED |
| `sshd` | maintenance access | startup script; config absent | VERIFIED (service), UNKNOWN (policy) |
| Broadcom BSA server | BLE provisioning/control bridge | startup script and BLE library | VERIFIED |
| `wcs-rd2xy`, `wcs-xy2rd`, `plot-constellations` | WCS/catalogue utilities | supplied ARM ELFs | VERIFIED |
| `skysegment.rknn` | neural sky segmentation | model config and RKNN dependency | HIGH |

`bilbo` is stripped but retains C++ RTTI, error strings, handler names, linked
component metadata, and serialized protobuf descriptors. `bilbo_upgrade` retains
debug information and symbol names. No binary was executed. **VERIFIED**
