# Troubleshooting

Start with the Control Center log and the newest file under `var/logs`. Redact the
items listed in [sensitive runtime state](configuration.md#sensitive-runtime-state)
before sharing a report.

| Symptom | Likely cause | How to check | How to fix |
| --- | --- | --- | --- |
| DWARF cannot be found | Wrong network mode, STA address changed, or client isolation | Compare the selected IP with the Provisioning status; test that the PC is on the same subnet | Reconnect to the DWARF AP, rediscover its STA address, or disable guest/client isolation |
| Alpaca server will not start | Port conflict, invalid setting, or failed hardware preflight | Open the newest startup log; run `Get-NetTCPConnection -LocalPort 11111` | Stop the conflicting process, change the HTTP port, or correct the model/IP |
| NINA cannot discover devices | UDP discovery blocked or NINA is scanning another interface | Confirm `/management/apiversions` locally; check private-network firewall permission and UDP 32227 | Allow the app on private networks or add Alpaca devices manually using the PC address and HTTP port |
| WebSocket/master lock fails | Official app or another client owns the DWARF | Search the log for `master_lock`; close other controllers | Close the DWARFLAB app, wait a few seconds, then restart dwarfAlp with the correct model |
| Camera cannot connect | Wrong model/client ID, wrong IP, or stale session | Compare Settings with the physical unit; inspect preflight and device-state events | Select the exact model, restore its profile client ID, verify the IP, and restart the server |
| Exposure fails | Unsupported parameter, missing mode transition, filter error, or safety/calibration requirement | Find `startexposure`, parameter, response code, and capture-state events in both dwarfAlp and NINA logs | Start with a supported short exposure/filter, calibrate if required, and preserve both sanitized logs for a report |
| Image never becomes ready | FITS finalization or FTP/HTTP retrieval is delayed/blocked | Confirm the telescope created a new FITS; inspect album, FITS-list, FTP, and timeout events | Keep the server running, verify ports 21/80/8082 are reachable, free device storage, then retry one frame |
| Second exposure says busy | Firmware has not returned to idle after the first capture | Search for capture-state notification `15208` and stop/recovery events | Wait for idle, reconnect the camera/server if state remains stale, and attach sanitized logs if reproducible |
| Filter wheel unavailable | DWARF 2 has none, or wrong model is selected | Check the advertised management devices and selected model | Do not add a wheel for DWARF 2; correct the model for DWARF 3/mini and rediscover equipment |
| BLE provisioning fails | Bluetooth permission/range, wrong BLE password, or unsupported network | Confirm the discovered address and exact failure in the log | Move closer, close the official app, verify credentials, and retry a 2.4 GHz SSID if required by the device |
| Calibration runs until timeout | Poor solve conditions, inaccurate coordinates, missing autofocus completion, or wrong workflow | Inspect autofocus, `11013`, solve-attempt, `15256`, and final calibration trace events | Verify coordinates and visible stars, focus first, select a real target in NINA, and allow multiple attempts |
| GUI executable does not open | Blocked download, unwritable folder, or packaging/runtime error | Check Windows Security and `var/logs`; developers can inspect `build/DwarfAlpacaGUI/warn-DwarfAlpacaGUI.txt` | Re-download from Releases, use a writable folder, allow the file, or report the sanitized startup log |

## Useful connectivity checks

Replace the addresses with the Windows PC and DWARF addresses respectively:

```powershell
Invoke-RestMethod http://127.0.0.1:11111/management/apiversions
Test-NetConnection 192.168.88.1 -Port 9900
Test-NetConnection 192.168.88.1 -Port 8082
Test-NetConnection 192.168.88.1 -Port 21
```

Do not disable the firewall globally. Create private-network rules for the executable
and required ports instead.
