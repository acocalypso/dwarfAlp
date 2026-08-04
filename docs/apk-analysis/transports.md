# HTTP, BLE, file transfer and RTSP

## Local HTTP

`DeviceHttpApi` constructs `http://<current-device-ip>:8082/` and uses the
application OkHttp client. APK 3.4.1's Retrofit `Api.java` registers 24 local
operation declarations across 21 distinct paths. The complete signatures and
source lines are in [api-inventory.json](api-inventory.json), and an OpenAPI
rendering is generated as `docs/site/device-openapi.json`. Cloud/account
operations live in separate Retrofit interfaces and are catalogued with a
`cloud` scope, not presented as local telescope control.

| Operation | Method/path | Authentication | Evidence | Confidence |
|---|---|---|---|---|
| Device API base | `http://<device>:8082/` | none observed at base builder | `DeviceHttpApi.a`, constructor | confirmed in app code |
| Device info | `POST /deviceInfo` | none in Retrofit declaration | `Api.java` | confirmed in app code |
| Shooting modes | `GET /shootingMode/getSupportedShootingModes`, `POST /shootingMode/getParamAndSetting` | none in declaration | `Api.java` | confirmed in app code |
| Album metadata | `POST /album/list/mediaCounts`, `POST /album/list/mediaInfos`, `POST /album/getMediaInfoByFilePath` | none in declaration | `Api.java` | confirmed in app code |
| FITS list | `POST /album/astro/fitsList` | none in declaration | `Api.java` | confirmed in app code |
| Album/FITS deletion | `POST /album/delete`, `DELETE /album/astro/deleteFits` | none in declaration | `Api.java` | confirmed; destructive |
| Device logs | `GET /logInfo`, `GET /downloadLog` | none in declaration | `Api.java` | confirmed in app code |
| Reset/activation | `/getResetState`, `/resetDeviceInfo`, activation endpoints | none in declaration | `Api.java` | confirmed; reset is destructive |
| Firmware upload | multipart `POST /uploadFirmware`, `/uploadFirmwareDiff` | none in declaration | `Api.java` | confirmed; destructive and out of driver scope |

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
