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

In the desktop app, every option on the **Settings** and **Capture** tabs can be
stored with
**File → Save settings profile** (`Ctrl+S`). It writes `dwarf-alpaca.yaml` in the
folder the app is started from (next to the executable for packaged builds), and
that file is loaded automatically at start-up. The **Capture** tab holds the
continuous-session and session-deletion options.

> **Disclaimer.** The DWARF 3 changes on this branch (continuous session, full
> resolution DSO capture, GOTO from NINA, session deletion) were tested only with a
> DWARF 3 running firmware V1.5.4.1 and V1.5.5.1 with DWARFLAB app V3.4.5 (build 794)
> and N.I.N.A. 3.2.0.9001 (see `docs/development/dwarf3-nina-field-tests.md`). DWARF 2
> and DWARF mini use the same code paths but have not been tested. DWARFLAB
> publishes no API, so newer firmware or app versions may change the behaviour.
> Use at your own risk, keep copies of your data, and report problems with the
> technical log.
>
> **NINA settings for the DWARF 3.** Options → Equipment → Telescope: focal length
> 150 mm, focal ratio 4.3 (ASTAP otherwise solves for a field four times too large).
> Options → Equipment → Camera → Camera Timeout: 180 s (NINA waits the exposure time
> plus this value). The first frame of a DWARF session arrives 1–2 minutes after
> the exposure ends (the DWARF closes the previous session and starts a new one);
> with NINA's default 60 s timeout NINA aborts and asks again.
> Exposure times must be one of the DWARF's own values (DWARF 3 astro mode, in
> seconds: 1, 1.3, 1.6, 2, 2.5, 3.2, 4, 5, 6, 8, 10, 13, 15, 30, 45, 60, 90, 120);
> other times are refused and Activity says so. Gain is 40–240 in steps of 10; a
> value in between is rounded to the nearest step. Other models: see
> `device-models.md`.
> The DWARF 3 filters are named **VIS**, **Astro** and **HO**, as in the DWARFLAB app
> (which called HO "Duo-Band" until 2026-11). NINA stores filters by name: after
> updating dwarfAlp, reconnect the filter wheel in NINA and update sequences that
> still use the old names ("VIS Filter", "Astro Filter", "Duo-Band Filter"). **File → Save settings profile as…**
writes to another file, which can be opened later with **Load settings profile…**.

Precedence, lowest to highest: defaults, `.env` and environment variables, the YAML
profile, then edits made on the Settings tab before starting the server. Values in a
loaded profile (IP, model, location, timezone) also win over those remembered from
BLE provisioning, until a new provisioning run replaces the IP.

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
| `autofocus_before_calibration` | Astro autofocus before the DWARF calibrates (GOTO, calibration after start). DWARF 3 firmware V1.5.4.1 never starts it, so it is off | `false` |
| `calibration_autofocus_timeout_seconds` | Required autofocus wait | `120` |
| `calibration_timeout_seconds` | Firmware solve/calibration wait | `300` |
| `calibration_wait_for_slew_seconds` | Combined calibration + slew wait | `420` |
| `auto_calibrate_on_slew` | Calibrate on first uncalibrated target slew | `true` |
| `ring_light_off` | Turn the DWARF ring light off when dwarfAlp connects (Capture tab) | `false` |
| `battery_indicator_off` | Turn the DWARF battery indicator off when dwarfAlp connects (Capture tab) | `false` |
| `always_one_click_goto` | Use the one-click GOTO for every slew, also after dwarfAlp calibrated (the plain GOTO did not move a DWARF 3 on firmware V1.5.4.1) | `true` |
| `calibrate_after_server_start` | Autofocus at startup; target calibration waits for slew | `false` |
| `focuser_target_tolerance_steps` | Position tolerance | `5` |

## Transport, provisioning, and simulation

| Field / environment suffix | Purpose | Default |
| --- | --- | --- |
| `http_timeout_seconds` / `http_retries` | Device HTTP timeout/retry count | `5` / `3` |
| `stream_buffer_seconds` | Live-stream buffer | `1.5` |
| `ftp_timeout_seconds` / `ftp_poll_interval_seconds` | FITS transfer timeout/poll interval | `10` / `1` |
| `delete_astro_session_after_download` | **Destructive.** After a FITS is downloaded, delete that capture's whole session (raw, stacked, previews) from the DWARF album via `POST /album/delete` | `false` |
| `delete_astro_session_timeout_seconds` | How long to wait for the album entry before skipping the deletion | `180` |
| `continuous_astro_session` | DWARF 3 light frames always use one continuous DWARF session (the DWARF always captures as a stacking session on the telescope); consecutive exposures with the same exposure, gain, filter and binning receive the next raw FITS. The session ends on settings change, abort, slew, tracking off, focuser move, filter change, disconnect or idle timeout. Not shown in the GUI; `false` is only a diagnostic fallback to one session per frame (CLI/env) | `true` |
| `continuous_astro_max_frames` | Frame count requested from the DWARF for a continuous session | `999` |
| `continuous_astro_idle_timeout_seconds` | Stop a continuous session after this long without a new exposure request | `120` |
| `astro_capture_ready_timeout_seconds` | How long a new capture waits for the DWARF to finish closing the previous session | `150` |
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
