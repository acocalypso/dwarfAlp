# Evidence index

All APK locations are relative to the ignored JADX source root. No proprietary
method bodies are copied here.

| ID | Source/location | Observation | Model/firmware | Confidence |
|---|---|---|---|---|
| EV-APK-01 | APK metadata and apksigner output | package/version/hash/signature baseline | app 3.4.1 | confirmed in app artifact |
| EV-ARCH-01 | `AndroidManifest.xml`; `base.App`; feature packages | component and application architecture | app 3.4.1 | confirmed in app code |
| EV-WS-01 | `defpackage/sp5.java:29,653`; `defpackage/m3a.java` | WS URL port 9900, OkHttp manager and binary send | all connection profiles | confirmed in app code |
| EV-WS-02 | `proto/BaseProto.java:29` | eight-field `WsPacket` descriptor | all | confirmed in app code |
| EV-WS-03 | `data/websocket/WsRequestHandle.java:87-116` | command-indexed response parsing/matching | all | confirmed in app code |
| EV-WS-04 | `data/bean/ws/WsCmd.java:181` | system master command registry value 13004 | registered profiles | confirmed in app code |
| EV-HTTP-01 | `net/api/deviceapi/DeviceHttpApi.java:186-204` | local HTTP base on device port 8082 | all | confirmed in app code |
| EV-BLE-01 | `defpackage/tn1.java:8-15` | DAF2–DAF6, DAF07, 180A and 9999 UUIDs | model-dependent | confirmed in app code |
| EV-CAP-01 | `WsStartCaptureRawLiveStackingReq.java:57`; Mini capture | `ir_index` and `force_start`; Astro=1, Duo=2 | Mini 1.1.3 build 2 | app code and hardware traffic |
| EV-CAP-02 | `WsCmd.java:130-136`; raw Mini survey | 11040/11041 params; 11043 calibration-list ambiguity | Mini 1.1.3 build 2 | mixed; individual claims labelled |
| EV-CAP-03 | `WsStartCaptureCaliFrameReq.java:73`; `WsCmd.java:135-136,347-348` | 11045/11046 and 15290/15291 calibration workflow | newer/Mini | confirmed in app code |
| EV-PARAM-01 | `assets/params_range.json`; `DeviceType.java` | complete exposure-code table and model/camera-specific ranges for published devices; IDs D2=1, D3=2, Mini=4 | app 3.4.1 | confirmed in app resource/code |
| EV-PARAM-02 | `FilterType.java`; `assets/params_range.json` | VIS=0, Astro=1, Duo-Band=2, Dark=3; normal choices differ by model | app 3.4.1 | confirmed in app resource/code; physical wheel positions unresolved |
| EV-CAP-04 | `WsStartCaptureRawLiveStackingReq.java`; `WsStartCaptureCaliFrameReq.java` | live-stacking start serializes filter/force-start only; calibration start carries all frame parameters | shared V3 workflow | confirmed in app code |
| EV-CAL-01 | `WsStartCalibrationReq.java:21-48`; `CaptureActivity.java:2597-2623,4629-4652`; `CaptureViewModel.java:8385-8391`; `AstroProto.java:38` | 11000 requires current longitude field 1 and latitude field 2; app blocks missing/(0,0) location | shared V3 workflow | confirmed in app code |
| EV-HW-01 | authorized Mini probes and user-observed app UI | Deep Sky offers Astro/Duo-Band and accepts 1 second | Mini 1.1.3 build 2 | confirmed on hardware |

PCAP frame-level references are maintained with sanitized decode outputs in
`dwarfii_api/tools/v3-probe/pcaps` and `PCAP_FINDINGS.md`. Private IP addresses,
device identifiers and credentials are not reproduced in repository docs.
