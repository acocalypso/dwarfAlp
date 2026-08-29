# Installation

The packaged Windows Control Center is the recommended installation for observers.
Python is not required for that route.

## Windows release

1. Open the [latest dwarfAlp release](https://github.com/acocalypso/dwarfAlp/releases/latest).
2. Download `DwarfAlpacaGUI-<version>-windows-x64.exe` and `SHA256SUMS.txt`.
3. Optionally verify the download in PowerShell:

   ```powershell
   Get-FileHash .\DwarfAlpacaGUI-*-windows-x64.exe -Algorithm SHA256
   ```

   Compare the displayed hash with `SHA256SUMS.txt`.
4. Move the executable to a writable folder such as
   `C:\Users\<you>\Applications\dwarfAlp` and run it.
5. If Microsoft Defender SmartScreen appears, verify that the file came from this
   repository's release page before choosing to run it. Releases are not code-signed.
6. Allow access on private networks when Windows Firewall asks. TCP port `11111` and
   UDP port `32227` are the defaults used by Alpaca.

Runtime state and logs are created under `var` beside the executable. Keep that folder
writable. Continue with [first run](first-run.md).

## Install from source

This route is useful for contributors and platforms without a packaged application.
It requires Python 3.10 or newer and [uv](https://docs.astral.sh/uv/).

```powershell
git clone https://github.com/acocalypso/dwarfAlp.git
cd dwarfAlp
python -m pip install uv
uv sync --locked
uv run dwarf-alpaca-gui
```

Use `uv run dwarf-alpaca --help` for the command-line server and provisioning tools.
Contributors should use the [development setup](../development/setup.md), which also
installs lint, test, protobuf, and packaging dependencies.

## Update or uninstall

To update a packaged installation, stop the server, download the newer executable,
and replace the old one. Preserve `var` only if you want to keep saved connectivity
state and logs. To uninstall, remove the executable and its `var` directory; review
the [credential warning](../user-guide/configuration.md#sensitive-runtime-state) first.
