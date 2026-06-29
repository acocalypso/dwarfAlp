# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the DWARF Alpaca Control Center GUI.

Cross-platform: PyInstaller resolves the data-file path separator itself, so the
same spec produces a Windows ``.exe`` and a Linux binary (the latter is wrapped
into an AppImage by ``scripts/build_appimage.sh``).

Build with::

    pyinstaller packaging/dwarf_alpaca_gui.spec
"""

import sys
from pathlib import Path

# Paths in a spec are resolved relative to the spec file's directory, so anchor
# everything at the repository root (the parent of packaging/) for robustness
# regardless of the working directory PyInstaller is invoked from. SPECPATH is
# injected by PyInstaller and points at this spec file's directory.
REPO_ROOT = Path(SPECPATH).resolve().parent
IMAGES = REPO_ROOT / "images"

# Windows gets the .ico (embedded into the executable); other platforms use the
# PNG (the AppImage desktop icon is handled separately by the build script).
if sys.platform.startswith("win"):
    icon_file = str(IMAGES / "dwarfalplogo.ico")
else:
    icon_file = str(IMAGES / "dwarfalplogo.png")

a = Analysis(
    [str(REPO_ROOT / "run_gui.py")],
    pathex=[str(REPO_ROOT / "src")],
    binaries=[],
    datas=[(str(IMAGES), "images")],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="DwarfAlpacaGUI",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_file,
)
