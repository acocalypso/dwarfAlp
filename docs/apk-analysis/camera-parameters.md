# Camera parameter tables

DWARFLAB 3.4.1 includes `assets/params_range.json`, which the app uses to
populate its camera controls. The tables below are derived interoperability
facts from that resource and the decompiled `DeviceType` and `FilterType`
enums. They are not inferred from the numeric spacing.

## Device identifiers

| Device | ID |
|---|---:|
| DWARF 2 | 1 |
| DWARF 3 | 2 |
| DWARF Mini | 4 |
| DWARF 4 | 5 |

DWARF 4 is present in the enum but has no entry in this APK's camera-parameter
resource. Camera ID 0 is tele and camera ID 1 is wide.

## Exposure lookup

The firmware exposure parameter is a lookup code, not milliseconds and not a
uniform index. Values from `1/10000` through `1/3` are fractions of a second;
all remaining labels are seconds.

| Code | Exposure | Code | Exposure | Code | Exposure |
|---:|---:|---:|---:|---:|---:|
| 0 | 1/10000 s | 3 | 1/8000 s | 6 | 1/6400 s |
| 9 | 1/5000 s | 12 | 1/4000 s | 15 | 1/3200 s |
| 18 | 1/2500 s | 21 | 1/2000 s | 24 | 1/1600 s |
| 27 | 1/1250 s | 30 | 1/1000 s | 33 | 1/800 s |
| 36 | 1/640 s | 39 | 1/500 s | 42 | 1/400 s |
| 45 | 1/320 s | 48 | 1/250 s | 51 | 1/200 s |
| 54 | 1/160 s | 57 | 1/125 s | 60 | 1/100 s |
| 63 | 1/80 s | 66 | 1/60 s | 69 | 1/50 s |
| 72 | 1/40 s | 75 | 1/30 s | 78 | 1/25 s |
| 81 | 1/20 s | 84 | 1/15 s | 87 | 1/13 s |
| 90 | 1/10 s | 93 | 1/8 s | 96 | 1/6 s |
| 99 | 1/5 s | 102 | 1/4 s | 105 | 1/3 s |
| 108 | 0.4 s | 111 | 0.5 s | 114 | 0.6 s |
| 117 | 0.8 s | 120 | 1 s | 123 | 1.3 s |
| 126 | 1.6 s | 129 | 2 s | 132 | 2.5 s |
| 135 | 3.2 s | 138 | 4 s | 141 | 5 s |
| 144 | 6 s | 147 | 8 s | 150 | 10 s |
| 153 | 13 s | 156 | 15 s | 159 | 30 s |
| 160 | 45 s | 162 | 60 s | 163 | 90 s |
| 165 | 120 s | 168 | 180 s | 171 | 240 s |
| 174 | 300 s | | | | |

The app-advertised normal ranges are:

| Device | Tele range | Wide range | Default |
|---|---:|---:|---:|
| DWARF 2 | 1–15 s | 1/10000–1 s | tele 15 s, wide 1 s |
| DWARF 3 | 1–120 s | 1–90 s | 15 s |
| DWARF Mini | 1–180 s | 1–30 s | 15 s |

The resource contains separate dark-frame ranges. Those ranges are device and
camera specific and must not be treated as proof that every value is valid for
a normal light capture on every firmware version.

## Filter values

| Value | Enum | Meaning |
|---:|---|---|
| -2 | `UNKNOWN` | invalid/unrecognized |
| -1 | `NONE` | no selected filter |
| 0 | `VIS` | visible-light filter |
| 1 | `ASTRO` | Astro filter |
| 2 | `DUO_BAND` | Duo-Band filter |
| 3 | `DARK` | internal dark/calibration position |

Normal tele-camera choices exposed by the APK are DWARF 2 `[VIS, ASTRO]`,
DWARF 3 `[VIS, ASTRO, DUO_BAND]`, and Mini `[ASTRO, DUO_BAND]`. Dark is
not a normal UI choice. The calibration-frame request explicitly carries
`DARK=3`; this proves the protocol value but not its physical wheel index.
In particular, the two DWARF 2 protocol choices do not imply that DWARF 2 has
a motorized filter wheel; they can represent its optical/IR-cut modes.

## Capture request consequence

The V3 live-stacking start request model has fields for exposure, gain, filter,
capture count, and force-start, but its serializer sends only filter and
force-start. Exposure, gain, resolution, and frame count therefore have to be
applied by their parameter commands before starting the capture. The
calibration-frame request is different: it serializes exposure, gain,
resolution, count, camera, calibration type, filter, and scene together.

## Evidence

- APK: DWARFLAB 3.4.1 APKS, `assets/params_range.json`
- Decompiled enums: `DeviceType`, `FilterType`
- Decompiled requests: `WsStartCaptureRawLiveStackingReq`,
  `WsStartCaptureCaliFrameReq`
