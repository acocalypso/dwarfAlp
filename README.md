<p align="center">
  <img src="images/dwarfalplogo.png" alt="dwarfAlp logo" width="180">
</p>

# dwarfAlp

> ASCOM Alpaca bridge for DWARFLAB smart telescopes.

[![Windows release](https://img.shields.io/github/v/release/acocalypso/dwarfAlp?label=Windows%20release)](https://github.com/acocalypso/dwarfAlp/releases/latest)
[![API documentation](https://github.com/acocalypso/dwarfAlp/actions/workflows/docs-pages.yml/badge.svg)](https://acocalypso.github.io/dwarfAlp/)
[![License: GPL-3.0](https://img.shields.io/badge/license-GPL--3.0-blue.svg)](LICENSE)

dwarfAlp makes a DWARFLAB telescope available to astronomy software through
ASCOM Alpaca. It is intended primarily for Windows users who want to control a
DWARF 2, DWARF 3, or DWARF mini from NINA, while keeping the DWARF protocol and
network handling inside one Control Center application.

## Project status

dwarfAlp is an independent, experimental open-source driver, not an official
DWARFLAB or ASCOM product. Device firmware changes may affect compatibility.
Start with an attended, short test exposure before using an automated sequence.

| Device | Telescope | Camera | Focuser | Filter wheel | Verification |
| --- | :---: | :---: | :---: | :---: | --- |
| DWARF 2 | Implemented | Implemented | Implemented | Not present | Automated tests; current hardware not physically verified |
| DWARF 3 | Implemented | Implemented | Implemented | Implemented | Automated tests and physical camera, focuser, filter, slew, and NINA capture tests |
| DWARF mini | Implemented | Implemented | Implemented | Implemented | Automated tests and physical camera/filter capture tests |

All three profiles use the shared V3 protocol family. “Automated tests” means
simulation and protocol mocks, not certification against every firmware version.
See [device support](docs/user-guide/device-models.md) for details.

## Features

- ASCOM Alpaca telescope, camera, and focuser devices
- Model-aware filter wheel support for DWARF 3 and DWARF mini
- NINA discovery, connection, slewing, focusing, and FITS capture
- Windows Control Center with model, address, location, and server settings
- Wi-Fi onboarding through BLE provisioning
- Simulation mode for setup without hardware
- Structured logs and a generated API/protocol reference

## Quick start

### 1. Install on Windows

1. Open the [latest GitHub release](https://github.com/acocalypso/dwarfAlp/releases/latest).
2. Download `DwarfAlpacaGUI-<version>-windows-x64.exe`.
3. Place it in a writable folder and start it. Windows may show an unrecognized-app
   warning because releases are not currently code-signed.
4. Allow private-network access if Windows Firewall asks. Alpaca discovery needs it.

See the [Windows installation guide](docs/getting-started/installation.md) if you
prefer to run from source or need release checksum instructions.

### 2. Connect the DWARF

1. Power on the telescope and connect the PC to the same network. The device can be
   in its own access-point (AP) mode or connected to your home network (STA mode).
2. In **Settings**, select the exact model and enter its reachable IP address.
3. Enter or fetch your observing coordinates if calibration or slewing will be used.
4. Select **Start server** and wait for the Control Center to report that the server
   is running.

Use the **Provisioning** tab if the DWARF still needs home-network credentials. The
[first-run guide](docs/getting-started/first-run.md) explains both network modes.

### 3. Connect NINA

With dwarfAlp still running, open NINA and scan for Alpaca equipment. Add the DWARF
camera, telescope, focuser, and—where supported—filter wheel, then connect them.
Follow the illustrated [NINA setup guide](docs/user-guide/nina.md) for the exact
order and discovery checks.

### 4. Verify safely

Begin with an attended short exposure. Indoors or in daylight, use very low gain and
a millisecond exposure on DWARF 2/3; ordinary astronomy values can saturate the
sensor. Confirm that NINA receives the FITS image before starting a sequence.

## Simulation

Simulation verifies the Alpaca server and NINA setup without connecting hardware.
Enable **Force simulation mode** in the Control Center, start the server, and connect
NINA normally. See [simulation mode](docs/getting-started/simulation.md).

## Documentation

- [Documentation home](docs/README.md)
- [Installation](docs/getting-started/installation.md) and [first run](docs/getting-started/first-run.md)
- [NINA setup](docs/user-guide/nina.md)
- [Configuration reference](docs/user-guide/configuration.md)
- [Capture behavior](docs/user-guide/capture.md)
- [Troubleshooting](docs/user-guide/troubleshooting.md)
- [Developer setup](docs/development/setup.md) and [contributing](CONTRIBUTING.md)
- [Protocol, APK, and firmware research](docs/research/README.md)
- [Generated API Observatory](https://acocalypso.github.io/dwarfAlp/)

## Known limitations

- Hardware verification covers specific devices and firmware, not every release.
- The DWARF remains responsible for calibration, tracking, safety limits, and much
  of the astronomy workflow; dwarfAlp translates the client requests.
- Graceful `StopExposure` is not advertised because distinct firmware behavior is
  unproven. The astronomy workflow supports abort.
- DWARF 2 has no built-in filter wheel and does not expose one through Alpaca.

## Contributing

Code, documentation, hardware observations, and sanitized protocol evidence are
welcome. Physical hardware is not required for ordinary contributions. Read
[CONTRIBUTING.md](CONTRIBUTING.md) for the reproducible development and validation
workflow.

## License

dwarfAlp is licensed under the [GNU General Public License v3.0](LICENSE).
