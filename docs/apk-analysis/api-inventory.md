# Device API inventory

The machine-readable [api-inventory.json](api-inventory.json) contains all 356
WebSocket commands, all 137 response/error codes, 50 Retrofit HTTP operations,
11 HTTP request models, eight BLE commands, and eight BLE UUIDs recovered from
the APK. It preserves declarations, literal or symbolic values, direction,
directly traceable request protobufs, notification payload handlers, and source
lines. It is generated with:

```text
uv run python scripts/extract_apk_api_inventory.py \
  build/reverse-engineering/apk/DWARFLAB_3.4.1_apkcube/jadx/sources \
  docs/apk-analysis/api-inventory.json \
  --markdown-output docs/apk-analysis/websocket-code-registry.md
```

Registration does not prove support on every model. The following table is the
human-oriented subset relevant to dwarfAlp and the current Mini investigation.
The generated registry also retains all 57 requests without a directly
traceable wrapper and all 46 notification declarations without a typed handler;
they remain named unknowns rather than receiving guessed payload schemas.

| Operation | Model | Transport | Endpoint/command | Request | Response/notification | Trigger | Evidence | Confidence |
|---|---|---|---|---|---|---|---|---|
| LAN connection | all | WS | port 9900 | URL client ID | binary frames | connect device | EV-WS-01 | confirmed in app code |
| Master mode | model-dependent | WS | 13004 / V3 captured lock exchange | master request | lock notification | connection init | EV-WS-04 + captures | app code and Mini traffic |
| Set time/timezone | all | WS | system registry | protobuf time values | common response | connection init | APK request wrappers | confirmed in app code |
| Camera open/close | D2/D3 | WS | 10000/10001 | camera open/empty stop | common response/state | enter/leave camera | APK registry + repository traffic history | app code |
| Parameter discovery | D2/D3 | WS | 10038 | empty | feature params | camera init | APK registry | app code; Mini times out |
| V3 quick-set list | V3 models | WS | 11040 | camera type | quick-set entries | Deep Sky setup | APK 3.4.1 + traffic | confirmed |
| V3 quick-set select | V3 models | WS | 11041 | exact `info_id` | selected ID/code | preset selection | APK 3.4.1 | confirmed in app code |
| V3 live parameter catalogue | V3 models | HTTP | `shootingMode/getParamAndSetting` | `{modeId:2}` | exposure/gain tables and IDs | Deep Sky setup | APK 3.4.1 + Mini hardware | confirmed |
| V3 exposure/gain | V3 models | WS | 16700/16701 | parameter ID, manual mode, value/index | 15264 + response | before capture | APK 3.4.1 + captures | confirmed |
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
| Device info | all | HTTP | `POST :8082/deviceInfo` | empty JSON object | `DeviceInfoResp` | connection/device page | APK Retrofit `Api.java` | confirmed in app code |
| Wi-Fi provisioning | all | BLE | DAFx + 9999 UUID family | BLE protobuf frames | config/list/STA messages | connection setup | EV-BLE-01 | confirmed in app code |
| Preview | all | RTSP/media | path model-dependent | stream setup | video frames | camera/focus UI | media components + repository behavior | strongly inferred/static |
| Final image retrieval | V3 models | HTTP/file | `album/list/mediaInfos`, `album/astro/fitsList`, then static port 80 path | list/download | FITS/JPEG | capture complete | APK 3.4.1 + hardware logs | confirmed paths; creation timing remains firmware-dependent |
| Firmware update | all | cloud HTTP + device update path | cloud endpoints separated | version/artifact metadata | OTA state | settings/update UI | OTA ViewModels/NetHttpApi | confirmed in app code, out of driver scope |

There is no evidence for an independent “move Mini filter wheel” command in the
normal Deep Sky workflow. Treating filter position 1 as a physical wheel move
caused NINA failure because Mini filter choice is carried by capture start.
