# Releases and generated documentation

## Windows executable

`.github/workflows/release-windows.yml` runs on `v*` tags or manual dispatch. It
installs locked dependencies, runs Ruff and pytest, builds the one-file GUI, uploads a
workflow artifact, and creates a GitHub release with a SHA-256 file.

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
