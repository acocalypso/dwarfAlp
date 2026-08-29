"""dwarfAlp ASCOM Alpaca server package for supported DWARF telescopes."""

from importlib.metadata import PackageNotFoundError, version

__all__ = ["__version__"]

try:
    __version__ = version("dwarf-alpaca")
except PackageNotFoundError:  # pragma: no cover - source tree without installation
    __version__ = "0+unknown"
