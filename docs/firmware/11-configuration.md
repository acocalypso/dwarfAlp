# Configuration reference

| File/area | Purpose | Important non-secret facts | Confidence |
|---|---|---|---|
| `default_params_configs.yaml` | shooting modes/settings | mode/technique support, ranges, defaults, common flags | VERIFIED |
| `bilbo_config.json` | main service configuration | application configuration exists | VERIFIED |
| `nginx.conf` | media HTTP | port 80, `/DWARF_mini`, permissive CORS | VERIFIED |
| `vsftpd.conf` | storage FTP | anonymous/local access and write operations enabled | VERIFIED |
| `hostapd.conf`, `udhcpd.conf` | access-point network | AP/DHCP configuration exists; secrets redacted | VERIFIED |
| `nvram_ap6256.txt`, Broadcom firmware | Wi-Fi chipset support | AP6256/Broadcom family | HIGH |
| IQ JSON files | camera tuning | IMX662 and OS02K10 AF/FF profiles | VERIFIED |
| factory JSON | manufacturing/fatigue operations | diagnostic configuration exists | VERIFIED |
| `/userdata/data/device.db` | live WCDB/SQLite state | album, capture, calibration, parameter layers, and schedule schemas | VERIFIED live; only non-secret structural/runtime values inspected |

Common setting IDs found in the shooting configuration include 100
`auto_calibration`, 101 `disable_host_slave`, 104 wide matching calibration,
and 105 auto shutdown. Meanings follow firmware comments/names; they are not
automatically exposed by DwarfAlp.

The AP files contain credential material. Its existence and role are documented,
but actual SSIDs/passwords/keys are intentionally excluded.

`as_ap.sh` contains a `DWARF3_` naming clue despite being shipped in a Mini
bundle. That may reflect shared V3 platform code rather than the runtime Mini
SSID. The discrepancy is retained and no model identity is inferred from it.

The live mode-2 (`DSO`) catalogue confirms:

- camera 0 is the filtered tele camera, with normal filter values Astro `1`
  and Duo-Band `2`, exposure codes through `168` (180 seconds), and the
  astronomy gain range 40-240;
- camera 1 has no filter parameter, exposes DSO durations through code `159`
  (30 seconds), and also reports an astronomy gain range of 40-240;
- `stackCount` accepts 1-999 and `mosaicCount` 1-249;
- `autoCalibration` is enabled in the live mode configuration;
- `GET /shootingMode/getSupportedShootingModes` is the accepted verb. Sending
  POST returns HTTP 501 on this firmware, while
  `POST /shootingMode/getParamAndSetting` is accepted.

`GET /getDefaultParamsConfig` reports the embedded Bilbo configuration version
1.1.3.2 even when the updater ledger/factory version file has been advanced.
This endpoint is therefore a better indicator of the actual application
payload than the update ledger alone. **VERIFIED live**

The acquired SQLite state resolves the persisted `param_type` layers:

- `0` is the default/base layer;
- `1` is the saved normal-settings layer;
- `2` is the current/runtime layer.

For DSO tele capture, the captured current layer held exposure 1 second, gain
60, filter 1, and stack count 1. This independently confirms why the active V3
parameter namespace can differ from the saved preset and why DwarfAlp must
reapply exposure/gain/count after discovering the active namespace. The mode
table also contains synthetic mode 1000 named `CURRENT_MODE`. **VERIFIED on the
acquired Mini snapshot**
