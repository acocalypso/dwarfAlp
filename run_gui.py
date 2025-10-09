from __future__ import annotations

import os
import sys
from pathlib import Path

from dwarf_alpaca.gui.app import main


def _set_working_directory() -> None:
    if getattr(sys, "frozen", False):
        base_dir = Path(sys.executable).resolve().parent
    else:
        base_dir = Path(__file__).resolve().parent
    os.chdir(base_dir)


if __name__ == "__main__":
    _set_working_directory()
    main()
