# Configuration reference

Settings come from defaults, a root `.env` file, environment variables, or an optional
YAML profile. Environment names are the uppercase field name prefixed with
`DWARF_ALPACA_`. For example:

```powershell
$env:DWARF_ALPACA_DWARF_DEVICE_MODEL = "dwarfmini"
$env:DWARF_ALPACA_DWARF_AP_IP = "192.168.178.90"
$env:DWARF_ALPACA_FORCE_SIMULATION = "false"
uv run dwarf-alpaca serve
```

A YAML profile contains the lowercase field names:

```yaml
dwarf_device_model: dwarf3
dwarf_ap_ip: 192.168.178.91
site_latitude: 52.52
site_longitude: 13.405
```

Load it with `uv run dwarf-alpaca serve --config profile.yaml`, or use **File > Load
settings profile** in the Control Center. GUI overrides are applied to the loaded
settings for that run; provisioning state can also supply the detected model and STA
address.

The tables below are derived from `src/dwarf_alpaca/config/settings.py`, which remains
the authoritative source.

## Server and discovery

| Field / environment suffix | Purpose | Default | Example |
| --- | --- | --- | --- |
| `http_host` | Alpaca bind address | `0.0.0.0` | `127.0.0.1` |
| `http_port` | Alpaca TCP port | `11111` | `11112` |
| `http_scheme` | Advertised HTTP scheme | `http` | `https` |
| `enable_https` | Enable TLS | `false` | `true` |
| `tls_certfile`, `tls_keyfile` | TLS certificate/key paths | unset | `cert.pem` |
| `http_advertise_host` | Override discovery host | unset/automatic | `192.168.1.20` |
| `discovery_enabled` | Answer Alpaca UDP discovery | `true` | `false` |
| `discovery_interface` | UDP bind interface | `0.0.0.0` | `192.168.1.20` |
| `discovery_port` | Alpaca discovery port | `32227` | `32227` |
| `state_directory` | Connectivity state and logs | `var` | `C:\dwarfAlp-state` |
| `profiles_path` | Optional profile-data path | unset | `profiles.yaml` |

## Device and site

| Field / environment suffix | Purpose | Default | Example |
| --- | --- | --- | --- |
| `dwarf_device_model` | Capability profile: `dwarf2`, `dwarf3`, `dwarfmini` | `dwarf3` | `dwarfmini` |
| `dwarf_ap_ip` | Reachable AP or STA address | `192.168.88.1` | `192.168.178.90` |
| `dwarf_ws_client_id` | WebSocket identity; normally profile-derived | DWARF 3 ID | leave profile default |
| `dwarf_http_port` / `dwarf_jpeg_port` | Device API/preview ports | `8082` / `8092` | `8082` |
| `dwarf_ws_port` / `dwarf_rtsp_port` / `dwarf_ftp_port` | Control/video/file ports | `9900` / `554` / `21` | `9900` |
| `network_mode` | Connection-mode label | `ap` | `sta` |
| `timezone_name` | Observer IANA time zone | unset | `Europe/Berlin` |
| `site_latitude` | Decimal degrees, north positive | unset | `52.52` |
| `site_longitude` | Decimal degrees, east positive | unset | `13.405` |
| `geolocation_lookup_url` | User-triggered public-IP estimate service | `https://ipwho.is/` | provider URL |

## Capture, focus, and calibration

| Field / environment suffix | Purpose | Default |
| --- | --- | --- |
| `go_live_before_exposure` / `go_live_timeout_seconds` | Warm preview before astronomy capture / timeout | `true` / `5` |
| `dwarf_mini_capture_mode` | Mini capture workflow (`astro` recommended) | `astro` |
| `allow_unverified_direct_photo` | Permit the unverified direct-photo route | `false` |
| `capture_start_evidence_timeout_seconds` | Wait for evidence after start | `3` |
| `allow_continue_without_darks` | Match app **Continue** behavior for missing/mismatched darks | `true` |
| `dark_check_timeout_seconds` | Dark-status wait | `5` |
| `camera_gain_command_timeout_seconds` | Gain command wait | `2` |
| `camera_disconnect_timeout_seconds` | Camera shutdown wait | `5` |
| `goto_command_timeout_seconds` | Initial GoTo response wait | `45` |
| `goto_completion_timeout_seconds` | GoTo completion wait | `120` |
| `goto_valid_seconds` | Recent-GoTo validity for capture | `300` |
| `calibration_valid_seconds` | Calibration reuse period | `900` |
| `calibration_autofocus_timeout_seconds` | Required autofocus wait | `120` |
| `calibration_timeout_seconds` | Firmware solve/calibration wait | `300` |
| `calibration_wait_for_slew_seconds` | Combined calibration + slew wait | `420` |
| `auto_calibrate_on_slew` | Calibrate on first uncalibrated target slew | `true` |
| `calibrate_after_server_start` | Autofocus at startup; target calibration waits for slew | `false` |
| `focuser_target_tolerance_steps` | Position tolerance | `5` |

## Transport, provisioning, and simulation

| Field / environment suffix | Purpose | Default |
| --- | --- | --- |
| `http_timeout_seconds` / `http_retries` | Device HTTP timeout/retry count | `5` / `3` |
| `stream_buffer_seconds` | Live-stream buffer | `1.5` |
| `ftp_timeout_seconds` / `ftp_poll_interval_seconds` | FITS transfer timeout/poll interval | `10` / `1` |
| `ws_ping_interval_seconds` | WebSocket heartbeat period | `5` |
| `temperature_refresh_interval_seconds` | Sensor temperature poll period | `5` |
| `temperature_stale_after_seconds` | Maximum cached-temperature age | `20` |
| `ble_adapter` | Optional Bluetooth adapter selector | unset |
| `ble_password` | Device BLE credential | unset |
| `ble_response_timeout_seconds` | BLE response wait | `15` |
| `provisioning_timeout_seconds` | Whole provisioning wait | `120` |
| `force_simulation` | Prevent physical device access | `false` |

## Logging

`dwarf-alpaca start` and the Control Center write timestamped startup logs to
`<state_directory>/logs/dwarf-alpaca-start-*.log`. The GUI also displays them in its
log pane. Logs intentionally include protocol states, response codes, timing, model,
and network addresses needed for diagnosis.

## Sensitive runtime state

`<state_directory>/connectivity.json` can contain Wi-Fi SSIDs and plaintext passwords,
the last BLE device address, STA IP, device model, coordinates, and error history.
`.env` and YAML profiles can contain BLE credentials, network details, and TLS key
paths. Logs can contain IP addresses, device identifiers, target coordinates, file
paths, and FITS metadata.

Never attach `connectivity.json`, `.env`, private keys, or an unreviewed profile to a
bug report. Before sharing logs, redact:

- Wi-Fi SSIDs/passwords and BLE passwords
- public/private IP addresses if they are considered sensitive
- Bluetooth addresses, device IDs, and WebSocket client IDs
- personal paths, exact observing coordinates, and target/image metadata as needed

Runtime/build/evidence work directories are ignored by Git, but ignore rules are not
a substitute for reviewing files before upload.
