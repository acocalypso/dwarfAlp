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

Common setting IDs found in the shooting configuration include 100
`auto_calibration`, 101 `disable_host_slave`, 104 wide matching calibration,
and 105 auto shutdown. Meanings follow firmware comments/names; they are not
automatically exposed by DwarfAlp.

The AP files contain credential material. Its existence and role are documented,
but actual SSIDs/passwords/keys are intentionally excluded.

`as_ap.sh` contains a `DWARF3_` naming clue despite being shipped in a Mini
bundle. That may reflect shared V3 platform code rather than the runtime Mini
SSID. The discrepancy is retained and no model identity is inferred from it.
