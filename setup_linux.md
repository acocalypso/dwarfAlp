# DWARF Alpaca on Linux

This guide covers running the DWARF 3 Alpaca server on Linux — both the
graphical **Control Center** (shipped as a portable **AppImage**) and the
`dwarf-alpaca` command-line interface. The Windows-focused walkthrough lives in
[`setup.md`](setup.md); this is its Linux counterpart.

---

## 1. Host prerequisites

The AppImage bundles Python and the PySide6/Qt runtime, but a few system pieces
must be present on the host:

| Need | Why | Debian/Ubuntu | Fedora |
| --- | --- | --- | --- |
| FUSE | Required to run any AppImage | `sudo apt install libfuse2` | `sudo dnf install fuse-libs` |
| Qt platform libs | PySide6 GUI rendering | `sudo apt install libgl1 libegl1 libxkbcommon0 libxcb-cursor0` | `sudo dnf install mesa-libGL libxkbcommon libxcb` |
| BlueZ | BLE provisioning (`Provisioning` tab / `guide`) | `sudo apt install bluez` | `sudo dnf install bluez` |

For BLE, make sure the Bluetooth service is running and you have a powered
adapter:

```bash
sudo systemctl enable --now bluetooth
bluetoothctl list      # confirm a controller is present (e.g. hci0)
```

> If you only need simulation mode or hardware that is already on your Wi-Fi,
> BlueZ is optional.

---

## 2. Run the GUI (AppImage)

1. Download `DwarfAlpacaGUI-x86_64.AppImage` from the project releases.
2. Make it executable and launch it:

   ```bash
   chmod +x DwarfAlpacaGUI-x86_64.AppImage
   ./DwarfAlpacaGUI-x86_64.AppImage
   ```

The Control Center opens on the **Server** tab. Usage of the Server,
Provisioning, and Settings tabs is identical to the Windows guide
([`setup.md`](setup.md) sections 2–5).

> **Where state is stored:** runtime state (`var/connectivity.json`, logs) is
> written **next to the `.AppImage` file**, mirroring the portable behaviour of
> the Windows `.exe`. Keep the AppImage in a writable directory (e.g. your home
> folder), not on a read-only mount. To store state elsewhere, set
> `DWARF_ALPACA_STATE_DIRECTORY=/absolute/path`.

### Bluetooth adapter on Linux

When a field or flag asks for a BLE **adapter**, Linux uses HCI device names
(`hci0`, `hci1`, …) — not the Windows-style device descriptions. Leave it blank
to use the default adapter, or pass `--adapter hci0` on the CLI.

---

## 3. Run the CLI

Install into an isolated environment (recommended) or a virtualenv:

```bash
# Isolated, with the console entry points on your PATH
pipx install dwarf-alpaca

# …or a regular virtualenv from a checkout
python -m venv .venv && . .venv/bin/activate
pip install -e .
bash gen_pb2.sh          # generate protobuf modules (needs protobuf-compiler)
```

Common commands (full table in the [README](README.md)):

```bash
# Simulation: serve synthetic devices, no hardware needed
DWARF_ALPACA_FORCE_SIMULATION=true dwarf-alpaca serve

# Hardware, all-in-one provision + serve
dwarf-alpaca start --ssid "MySSID" --password "MyPassword"

# Interactive BLE onboarding using a specific adapter
dwarf-alpaca guide --adapter hci0 --ble-password DWARF_12345678
```

Settings come from `DWARF_ALPACA_*` environment variables, a `.env` file, or a
YAML profile via `--config`. Unlike the Windows guide's PowerShell syntax, use
POSIX shell exports:

```bash
export DWARF_ALPACA_HTTP_PORT=11800
export DWARF_ALPACA_FORCE_SIMULATION=true
dwarf-alpaca serve
```

---

## 4. Firewall

Alpaca clients reach the server over TCP (HTTP, default `11111`) and UDP
discovery (default `32227`). With `ufw`:

```bash
sudo ufw allow 11111/tcp
sudo ufw allow 32227/udp
```

---

## 5. Run as a background service (optional)

To keep the server running headless, install a per-user systemd unit at
`~/.config/systemd/user/dwarf-alpaca.service`:

```ini
[Unit]
Description=DWARF Alpaca server
After=network-online.target bluetooth.target

[Service]
Type=simple
WorkingDirectory=%h/dwarf-alpaca
ExecStart=%h/.local/bin/dwarf-alpaca serve
Restart=on-failure

[Install]
WantedBy=default.target
```

Then enable it:

```bash
systemctl --user daemon-reload
systemctl --user enable --now dwarf-alpaca
journalctl --user -u dwarf-alpaca -f   # follow logs
```

Adjust `WorkingDirectory` so that the portable `var/` directory lands where you
want state stored (or set `DWARF_ALPACA_STATE_DIRECTORY` in the unit's
`Environment=`).

---

## 6. Building the AppImage yourself

From a checkout with `protobuf-compiler`, `pyinstaller`, and the Qt/FUSE
libraries above installed:

```bash
pip install -e . pyinstaller
bash scripts/build_appimage.sh
# -> dist/DwarfAlpacaGUI-x86_64.AppImage
```

The script freezes the GUI with `packaging/dwarf_alpaca_gui.spec`, assembles an
AppDir (binary, `.desktop`, icon, `AppRun`), and wraps it with `appimagetool`.

---

## 7. Configure NINA and other clients

Client setup is platform-independent — follow [`setup.md`](setup.md) section 6.
Point clients at the host/port the server reports; if running NINA on Windows
against a Linux host, make sure the Linux firewall (section 4) allows the Alpaca
ports.
