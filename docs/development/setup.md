# Development setup

Development supports Python 3.10 or newer. The lock file and `uv` provide the
reproducible environment used by automation.

```powershell
git clone https://github.com/acocalypso/dwarfAlp.git
cd dwarfAlp
python -m pip install uv
uv sync --extra development --locked
```

Run the standard checks before editing to confirm the checkout:

```powershell
uv run ruff check .
uv run pytest -p no:cacheprovider
uv run python scripts/generate_protos.py --check
```

## Run locally

Start the GUI:

```powershell
uv run dwarf-alpaca-gui
```

Start a hardware-free CLI server:

```powershell
$env:DWARF_ALPACA_FORCE_SIMULATION = "true"
$env:DWARF_ALPACA_DISCOVERY_ENABLED = "false"
uv run dwarf-alpaca serve
```

For configuration, use environment variables, `.env`, or a YAML overlay documented
in the [configuration reference](../user-guide/configuration.md). Do not commit local
credentials or runtime state.

## Repository map

- `src/dwarf_alpaca/` — installable package and generated protobuf bindings
- `tests/` — unit, integration, simulation, and opt-in hardware tests
- `scripts/` — repository generation/maintenance commands
- `tools/` — standalone protocol and firmware research utilities
- `docs/site/` — authored Pages shell plus generated data
- `firmware-analysis/metadata/` — curated, tracked firmware evidence

Read [architecture](architecture.md) before changing session ownership, transports,
capture state, or device routers.
