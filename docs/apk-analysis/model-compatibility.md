# Model compatibility and repository gaps

| Capability | DWARF 2 | DWARF 3 | DWARF Mini | Firmware dependency | Evidence |
|---|---|---|---|---|---|
| WS default | 1.2/device 1 | 1.2/device 1 | 1.20/device 4 | yes | repository history; Mini capture |
| Client identity | DAF2 | DAF3 | DAF4 | probably model | APK UUID registry |
| Normal filters | none advertised | VIS/Astro/Duo-Band | Astro/Duo-Band | yes | D3 docs; Mini app and UI |
| Mini capture filter | n/a | unknown | 11005 `ir_index` 1/2 | newer profile | APK + Mini traffic |
| Dark filter | legacy dark workflow | legacy/new workflow unknown | 11045 filter 3 | newer profile | APK code; output unverified |
| V2 feature params 10038 | supported family | supported family | timeout observed | yes | docs/Mini hardware |
| V3 tuple params 11040/11041 | unknown | must not assume absent | verified | yes | APK + Mini traffic |
| GOTO | legacy commands | legacy commands | same high-level registry/profile | yes | APK/repository; Mini partial |
| Capture stop | 11006 family | 11006 family | 11006 family | semantics may differ | APK |
| Photo-workflow abort | unverified | unverified | rejected | yes | Mini hardware |
| Calibration completion/file | unverified | unverified | unverified | yes | capture still required |

## Gap analysis

| Finding | APK/capture behavior | Previous repository behavior | Required change | Status |
|---|---|---|---|---|
| Mini appeared seven times in NINA | one physical session was represented by multiple Alpaca identities/discovery responses | device enumeration/discovery handling was too broad | stable unique IDs and one management entry per Alpaca device type | implemented in prior Mini work, regression-tested |
| Duo-Band move failed | Mini applies `ir_index=2` in 11005 | filter setter attempted immediate wheel-like control | cache selection and apply at exposure start | implemented and tested |
| Astro is not “no filter” | Mini UI always exposes Astro or Duo-Band in Deep Sky | no-filter assumptions could leak from D3 | Mini profile has exactly two normal labels | implemented and tested |
| Dark is calibration-only | 11045/11046 with dark=3 | normal FilterWheel abstraction cannot select it | keep out of normal names; feature-gate Light=false after output capture | schema documented; production disabled |
| 1-second exposure | app/hardware accepts exact 11041 tuple | resolver required returned firmware value | allow evidence-backed exact tuple and require echo | implemented and tested |
| Abort error | photo workflow rejects abort | capability could be over-advertised | expose per-workflow non-support honestly | implemented in prior hardening |
| 11043 ambiguity | APK calls it calibration-frame list | decoder labeled response as exposure presets | do not rename payload semantics without raw response | documented unresolved |
| Generated protobufs | runtime imports `_pb2.py` directly | files were globally ignored and `--check` failed on clean state | version generated bindings and validate exact generation | corrected in this analysis |
| Command inventory drift | command lists were manually scattered | no reproducible APK registry export | evidence-preserving extractor and JSON | added in this analysis |

DWARF 3 remains a legacy-v2 default in production because this investigation
did not include DWARF 3 hardware. The APK's newer commands are documented but
are not enabled for DWARF 3 merely because they exist.
