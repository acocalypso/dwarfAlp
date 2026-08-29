# Releases and generated documentation

## Windows executable

`pyproject.toml` is the single declared project-version source. The package reads that
installed metadata at runtime, and the Control Center displays it in its title and
**Help > About dwarfAlp** dialog.

`.github/workflows/release-windows.yml` runs on manual dispatch or a matching `v*`
tag. It reads `[project].version`, derives the release tag (`0.1.0` becomes `v0.1.0`),
installs locked dependencies, runs Ruff and pytest, builds the one-file GUI, uploads a
versioned workflow artifact, and creates the matching GitHub release with generated
release notes and a SHA-256 file. Manual runs no longer ask for a separate version.

To prepare the next release, update `version` in `pyproject.toml`, refresh `uv.lock`,
commit and push the change, and manually run **Build and release Windows executable**.
If the workflow is started by pushing a tag, that tag must exactly match the derived
project tag or the job fails.

Reproduce its build on Windows:

```powershell
New-Item -ItemType Directory -Path var -Force | Out-Null
uv run pyinstaller `
  --noconfirm `
  --clean `
  --onefile `
  --windowed `
  --name DwarfAlpacaGUI `
  --icon "images\dwarfalplogo.ico" `
  --add-data "images;images" `
  --add-data "var;var" `
  --collect-data "tzdata" `
  --copy-metadata "dwarf-alpaca" `
  --paths "src" `
  "run_gui.py"
```

The result is `dist/DwarfAlpacaGUI.exe`. `run_gui.py` and `images/` stay in their
current locations because both the workflow and frozen-runtime asset resolution use
them. The local `DwarfAlpacaGUI.spec` is generated/ignored and is not a clean-checkout
build input.

## GitHub Pages

`.github/workflows/docs-pages.yml` regenerates and publishes `docs/site/` after
relevant changes on `main`. Generate locally with:

```powershell
uv run python scripts/generate_api_site.py
uv run python -m http.server 8000 --directory docs/site
```

Then open <http://127.0.0.1:8000>. The generated JSON files are API/inventory output;
`index.html`, `swagger.html`, CSS, and JavaScript are the authored presentation shell.
Do not manually patch generated JSON—change its source or generator instead.

The APK inventory and WebSocket registry have a separate regeneration step documented
in [APK analysis](../apk-analysis/README.md).
