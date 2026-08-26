# Device protocol reference

The primary control transport is WebSocket with protobuf payloads. The
`bilbo` ELF embeds complete serialized descriptors for 16 `.proto` files:
`astro`, `base`, `ble`, `camera`, `device`, `factoryTest`, `focus`,
`motor_control`, `notify`, `panorama`, `param`, `shooting_schedule`, `system`,
`task_center`, `track`, and `voice_assistant`. The recovered descriptor set
SHA-256 is
`4370a369cb1d151d052efbdaa8fd251658d3ced898dbe264aa01b612fa7aaf24`.
**VERIFIED**

## High-value exact schemas

| Message | Wire fields | Meaning | Confidence |
|---|---|---|---|
| `ReqStartCalibration` | `1 lon:double`, `2 lat:double` | begin astronomy calibration at location | VERIFIED |
| `ReqGotoDSO` | `1 ra`, `2 dec`, `3 target_name`, `4 goto_only`, `5 rotation?` | slew/goto target | VERIFIED |
| `ReqCaptureRawLiveStacking` | `1 ir_index:int32`, `2 force_start:bool` | start raw live stacking | VERIFIED |
| `ResAstroShooting` | `1 code`, `2 exp_name?`, `3 gain`, `4 resolution`, `5 filter_type`, `6 temp_threshold` | accepted/effective astro parameters | VERIFIED |
| `ReqContinueShooting` | empty | continue after a firmware warning | VERIFIED |
| `ReqSetLocation` | lat/lon/alt plus address fields and enable | persist location | VERIFIED |
| `ReqAstroAutoFocus` | `1 mode:uint32` | request astro autofocus | VERIFIED |
| `ReqMotorRunTo` | id, end position, speed, ramp, resolution | direct motor target | VERIFIED; unsafe for public use |

## Whole-device state (`16405`)

The recovered `task_center.proto` proves command `16405` is a device-state
query, not a static configuration blob:

```text
ReqGetDeviceStateInfo {}
ResGetDeviceStateInfo {
  shooting_mode = 1
  tele_camera_state_info = 2
  wide_camera_state_info = 3
  focus_state_info = 4
  motion_state_info = 5
  device_state_info = 6
  code = 7
  connection_state_info = 8
  supported_shooting_modes = 9 repeated
  wide_focus_state_info = 10
  guide_focus_state_info = 11
}
```

The tele camera state includes horizontal/vertical FOV, resolution, optional
CMOS temperature, stream state, and a oneof exclusive operation. Capture-raw
state uses `0 idle`, `1 running`, `2 stopping`, `3 stopped`. The device state
contains a calibration result (`azi`, `alt`). **VERIFIED**

The complete machine-readable descriptor inventory is
`firmware-analysis/metadata/bilbo-protos.json`. Command-number bindings still
come from APK/capture evidence because the embedded descriptors define payloads,
not the outer WebSocket dispatch IDs.

## Local HTTP routes proven by firmware strings

- `POST /album/getMediaInfoByFilePath`
- `DELETE /album/astro/fitsList`
- `DELETE /album/astro/deleteFits`
- `/shootingMode/getSupportedShootingModes`
- `/shootingMode/getParamAndSetting`
- `/mcufirmwareVersion`, `/sec`, `/checkMd5`
- `/raw_jpg?stack=(\d+)(?:&bits=(\d+))?`

The method for `/album/astro/fitsList` conflicts with newer APK evidence, which
uses POST. This is recorded as a firmware-version/API-version discrepancy and
must be negotiated or validated rather than guessed. **VERIFIED discrepancy**
