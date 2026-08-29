# Testing and quality checks

Install development dependencies first:

```powershell
uv sync --extra development --locked
```

## Standard validation

```powershell
uv run ruff check .
uv run pytest -p no:cacheprovider
uv run python scripts/generate_protos.py --check
uv run python scripts/check_markdown_links.py
uv run python scripts/generate_api_site.py
```

Ordinary tests use mocks, temporary state, and simulation. They do not require a
DWARF. New protocol behavior should include request encoding, response/notification,
error, and state-transition tests where applicable.

## Hardware tests are opt-in

Never set the hardware flag unless the selected telescope is powered, attended,
reachable, and safe to connect. The tracked mini smoke test acquires the master lock
and opens the camera, but performs no GoTo, focus movement, or capture.

```powershell
$env:DWARF_ALPACA_RUN_HARDWARE = "1"
$env:DWARF_ALPACA_DWARF_DEVICE_MODEL = "dwarfmini"
$env:DWARF_ALPACA_DWARF_AP_IP = "192.168.88.1"
uv run pytest -m hardware tests/test_hardware_mini.py
```

The `hardware` marker is skipped without the explicit runtime flag and is never set
in normal CI. Additional physical tests must state possible motion/capture effects and
fail closed when their opt-in prerequisites are absent.

## Manual smoke tests

- Import: `uv run python -c "import dwarf_alpaca; import dwarf_alpaca.gui.app"`
- CLI: `uv run dwarf-alpaca --help`
- Simulation: start the server and request `/management/apiversions`
- GUI: launch it, select simulation, start/stop the server, then close normally
- Release: reproduce the command in [releases](releases.md) on Windows
