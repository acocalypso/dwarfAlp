from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from dwarf_alpaca.config.settings import Settings, load_settings  # noqa: E402
from dwarf_alpaca.gui.app import (  # noqa: E402
    PROFILE_KEYS,
    read_profile_keys,
    write_profile,
)


def test_profile_round_trip(tmp_path: Path) -> None:
    settings = Settings(
        dwarf_ap_ip="192.168.88.1",
        site_latitude=40.4168,
        site_longitude=-3.7038,
        timezone_name="Europe/Madrid",
        delete_astro_session_after_download=True,
        delete_astro_session_timeout_seconds=240.0,
    )
    path = tmp_path / "dwarf-alpaca.yaml"

    write_profile(path, settings)
    loaded = load_settings(str(path))

    assert read_profile_keys(path) == set(PROFILE_KEYS)
    for key in PROFILE_KEYS:
        assert getattr(loaded, key) == getattr(settings, key), key


def test_profile_overrides_environment(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DWARF_ALPACA_FORCE_SIMULATION", "true")
    path = tmp_path / "dwarf-alpaca.yaml"
    write_profile(path, Settings(force_simulation=False))

    assert load_settings(str(path)).force_simulation is False
