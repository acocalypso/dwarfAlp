"""Cross-platform path helpers shared by the CLI and GUI."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def portable_base_dir() -> Path:
    """Return the directory that portable runtime state lives next to.

    The server keeps its state (``var/``: ``connectivity.json``, logs, etc.)
    alongside the distributed artifact so a release is self-contained. The
    resolution differs by how the app is being run:

    * **AppImage** – the binary executes from a read-only FUSE mount, so
      ``sys.executable`` points *inside* that mount. AppImage exposes the real
      on-disk path of the ``.AppImage`` file via the ``APPIMAGE`` environment
      variable; state therefore lives next to that file.
    * **PyInstaller .exe / onefile** – next to the bundled executable.
    * **Source checkout** – the current working directory.
    """

    appimage = os.environ.get("APPIMAGE")
    if appimage:
        return Path(appimage).resolve().parent
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path.cwd()


def bundled_resource_dir() -> Path:
    """Return the directory containing bundled data resources (``images/``).

    When frozen by PyInstaller, data added via ``--add-data`` is extracted to a
    temporary directory exposed as ``sys._MEIPASS``. In a source checkout the
    resources live at the repository root.
    """

    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    # src/dwarf_alpaca/paths.py -> repository root
    return Path(__file__).resolve().parents[2]
