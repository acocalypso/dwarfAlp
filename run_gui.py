from __future__ import annotations

import os

from dwarf_alpaca.gui.app import main
from dwarf_alpaca.paths import portable_base_dir


def _set_working_directory() -> None:
    os.chdir(portable_base_dir())


if __name__ == "__main__":
    _set_working_directory()
    main()
