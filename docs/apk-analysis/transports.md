# HTTP, BLE, file transfer and RTSP

## Local HTTP

`DeviceHttpApi` constructs `http://<current-device-ip>:8082/` and uses the
application OkHttp client. Traced operations include device information, media
metadata/download and device-log operations. Decompiled coroutine bodies for
some endpoints are incomplete, so endpoint path/method pairs that are not
independently present in captures remain unresolved. Cloud/account/update
operations live in the separate `NetHttpApi` and are not part of local Alpaca
control.

| Operation | Method/path | Authentication | Evidence | Confidence |
|---|---|---|---|---|
| Device API base | `http://<device>:8082/` | none observed at base builder | `DeviceHttpApi.a`, constructor | confirmed in app code |
| Device info | unresolved path | unknown | `DeviceHttpApi.deviceInfo` response type `DeviceInfoResp` | confirmed call, path unknown |
| Media operations | unresolved paths | unknown | `MediaInfoRequest`, `DeviceHttpApi` methods | confirmed call, paths unknown |
| Device logs | unresolved paths | unknown | `LogInfoBean`, `DeviceHttpApi` methods | confirmed call, paths unknown |

## BLE provisioning

The APK registers these Bluetooth-base UUIDs:

| UUID suffix | Full UUID | Observed role |
|---|---|---|
| 180A | `0000180A-0000-1000-8000-00805F9B34FB` | standard device information service |
| DAF2 | `0000DAF2-0000-1000-8000-00805F9B34FB` | DWARF 2 identity/service family |
| DAF3 | `0000DAF3-0000-1000-8000-00805F9B34FB` | DWARF 3 identity/service family |
| DAF4 | `0000DAF4-0000-1000-8000-00805F9B34FB` | DWARF Mini identity/service family |
| DAF5 | `0000DAF5-0000-1000-8000-00805F9B34FB` | registered; semantic role unresolved |
| DAF6 | `0000DAF6-0000-1000-8000-00805F9B34FB` | registered; semantic role unresolved |
| DAF07 | `000DAF07-0000-1000-8000-00805F9B34FB` | registered exactly as shown; role unresolved |
| 9999 | `00009999-0000-1000-8000-00805F9B34FB` | characteristic used by connection flow; direction needs capture |

The app and dwarfAlp protobufs expose get-config, AP/STA state, Wi-Fi list,
Wi-Fi credential submission, reset and system-info messages. The reconstructed
provisioning sequence is discovery, GATT connection, config query, Wi-Fi scan,
credential submission, STA polling/IP retrieval, BLE disconnect and WebSocket
connection. Encryption/checksum claims are intentionally omitted until raw
GATT traffic is captured.

## File and media transfer

dwarfAlp currently supports its evidence-backed FTP/file workflow and RTSP
preview. The 3.4.1 static pass did not establish new credentials or paths with
enough confidence to publish them. Credentials, if found in future work, must
be treated as security-sensitive and not copied into this report.

Capture completion is not inferred from an old newest file. The driver records
a file baseline, waits for device state/progress, then accepts only newly
created output matching the capture. This stale-file guard is repository
behavior and remains necessary even when the app uses album notifications.

RTSP is used for preview and focus feedback. Existing protocol notes state that
long exposure can switch preview delivery from RTSP to JPEG; it is not evidence
that preview frames are the final FITS capture result. Exact stream paths and
codec/model variations remain capture-dependent.
