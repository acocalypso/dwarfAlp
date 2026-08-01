# Device API inventory

The machine-readable [api-inventory.json](api-inventory.json) contains all 314
WebSocket commands recovered from the APK `WsCmd` registry, their declaration
line, literal or preserved symbolic value, direction, and directly traceable
request wrapper/protobuf builder. It is generated with:

```text
uv run python scripts/extract_apk_api_inventory.py \
  build/apk-audit-3.4.1/decompiled/sources \
  docs/apk-analysis/api-inventory.json
```

Registration does not prove support on every model. The following table is the
human-oriented subset relevant to dwarfAlp and the current Mini investigation.

| Operation | Model | Transport | Endpoint/command | Request | Response/notification | Trigger | Evidence | Confidence |
|---|---|---|---|---|---|---|---|---|
| LAN connection | all | WS | port 9900 | URL client ID | binary frames | connect device | EV-WS-01 | confirmed in app code |
| Master mode | model-dependent | WS | 13004 / V3 captured lock exchange | master request | lock notification | connection init | EV-WS-04 + captures | app code and Mini traffic |
| Set time/timezone | all | WS | system registry | protobuf time values | common response | connection init | APK request wrappers | confirmed in app code |
| Camera open/close | D2/D3 | WS | 10000/10001 | camera open/empty stop | common response/state | enter/leave camera | APK registry + repository traffic history | app code |
| Parameter discovery | D2/D3 | WS | 10038 | empty | feature params | camera init | APK registry | app code; Mini times out |
| V3 parameter get | Mini tested | WS | 11040 | mode | pipe-delimited presets | Deep Sky setup | Mini traffic | app code and hardware traffic |
| V3 parameter set | Mini tested | WS | 11041 | exact pipe tuple | echoed tuple/code | exposure/gain/frame apply | Mini traffic | app code and hardware traffic |
| Filter at capture | Mini | WS | 11005 | `ir_index`, `force_start` | common response + state/progress | start Deep Sky | EV-CAP-01 | app code and hardware traffic |
| Stop live stack | all profiles | WS | 11006 | empty | common response/state | stop capture | APK registry | app code; model semantics vary |
| Calibration-frame list | newer profile | WS | 11043 | request wrapper | unresolved payload | calibration UI | EV-CAP-02 | app code; response meaning unresolved |
| Start calibration frame | Mini/newer | WS | 11045 | exp, gain, resolution, count, camera, type, optional filter, scene | 15290/15291 | dark/calibration UI | EV-CAP-03 | confirmed in app code |
| Stop calibration frame | Mini/newer | WS | 11046 | camera type | state notification | stop calibration | EV-CAP-03 | confirmed in app code |
| GOTO DSO | D2/D3/Mini profile | WS | 11002 | RA degrees, declination, target | GOTO notifications | already calibrated target selected | APK wrapper + captures/history | app code |
| One-click calibration + GOTO DSO | D2/D3/Mini V3 | WS | 11013 | RA hours, declination, target, lon, lat, shooting mode, goto-only, optional rotation | 15210, 15233, 15256, tracking | Atlas target selected | `WsOneClickGotoDsoReq`, `CaptureViewModel.S6` | app code + official-app hardware observation |
| GOTO stop | all profiles | WS | 11004 | empty | common response/state | stop slew | APK registry | confirmed in app code |
| Focus step/continuous/stop | profile-specific | WS | focus command family | direction/step or speed | focus position/state | focus UI | APK focus wrappers | confirmed in app code |
| Battery/storage/temperature | all, capability-dependent | WS | notify family | unsolicited | state payload | device updates | APK response handlers | confirmed in app code |
| Device info | all | HTTP | port 8082, path unresolved | GET-like coroutine call | `DeviceInfoResp` | connection/device page | EV-HTTP-01 | base confirmed; path unknown |
| Wi-Fi provisioning | all | BLE | DAFx + 9999 UUID family | BLE protobuf frames | config/list/STA messages | connection setup | EV-BLE-01 | confirmed in app code |
| Preview | all | RTSP/media | path model-dependent | stream setup | video frames | camera/focus UI | media components + repository behavior | strongly inferred/static |
| Final image retrieval | model/workflow-dependent | file/HTTP/FTP | path model-dependent | list/download | FITS/JPEG | capture complete | repository captures/history | not newly verified by APK pass |
| Firmware update | all | cloud HTTP + device update path | cloud endpoints separated | version/artifact metadata | OTA state | settings/update UI | OTA ViewModels/NetHttpApi | confirmed in app code, out of driver scope |

There is no evidence for an independent “move Mini filter wheel” command in the
normal Deep Sky workflow. Treating filter position 1 as a physical wheel move
caused NINA failure because Mini filter choice is carried by capture start.
