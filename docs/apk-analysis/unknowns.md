# Unknowns and recommended captures

| Unknown | Model/firmware | Action | Transport/evidence needed | Distinguishing result |
|---|---|---|---|---|
| 11043 response schema | Mini 1.1.3 build 2 | open calibration-frame list after zero and after one dark set | raw WS request/response plus app screen | proves list element fields and whether it ever carries exposure presets |
| Dark output delivery | Mini 1.1.3 build 2 | create one dark set with known exposure/gain/count | WS 11045, 15290/15291, album/HTTP/file trace | final state, filename, format and retrievable image |
| Dark stop semantics | Mini 1.1.3 build 2 | start count >3, stop from app | WS timestamps and resulting files | acknowledgement, terminal state and partial-file policy |
| 11040 unknown tuple fields 1,2,6 | Mini | vary one app control at a time | before/after 11040/11041 payloads | maps each field without guessing |
| Exact RTSP paths/codecs | each model | enter tele/wide preview and switch modes | RTSP setup/describe plus media metadata | camera-to-path and codec mapping |
| Raw HTTP body/response fields | current firmware | exercise activation, reset-state, log and firmware-update screens without invoking destructive actions | authorized HTTP PCAP | schemas for operations whose Retrofit signature uses raw `RequestBody` |
| 50 request commands without a traced wrapper | current APK | trigger one UI control at a time | raw WS plus matching UI action | request protobuf or confirmation that the command uses an empty payload |
| Notification payloads without handler types | current APK | exercise the corresponding device state | unsolicited WS frames plus app display | protobuf schema and terminal-state meaning |
| BLE characteristic roles/framing | each model | provision a disposable test SSID | Android Bluetooth HCI snoop, sanitized | read/write/notify UUID roles, segmentation, retry and STA-IP message |
| DWARF 3 newer-profile use | DWARF 3, current firmware | connect app 3.4.1 and enter Deep Sky | initial WS envelopes and parameter commands | whether D3 negotiates 1.2, 1.20 or another profile and uses 10038 vs 11040 |
| Photo abort support | Mini | start a safely long direct-photo exposure and press app stop | WS plus final state/file | device command, response and whether physical exposure stops |
| Time warning of 7200 s | Mini | connect once with Berlin summer time, capture time/timezone exchange | WS request fields and device clock readback | separates UTC epoch from local-zone offset/double application |

## Safe Mini verification procedure

Close the DWARFLAB app before dwarfAlp testing unless the test explicitly
compares app traffic. Keep the telescope parked and lens unobstructed except for
dark-frame tests. Run hardware tests only with:

```text
$env:DWARF_ALPACA_RUN_HARDWARE='1'
$env:DWARF_ALPACA_DWARF_DEVICE_MODEL='dwarfmini'
$env:DWARF_ALPACA_DWARF_AP_IP='<authorized-device-ip>'
uv run pytest -m hardware --device dwarfmini -q
```

The current pytest version does not define a `--device` option, so until that
option is implemented use `uv run pytest -m hardware -q`; the environment
variable restricts the existing test to Mini. Do not run dark capture from
NINA until the output-delivery capture above has been decoded and a regression
fixture exists.
