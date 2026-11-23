"""Shared test fixtures."""

from __future__ import annotations

import os

import pytest

from dwarf_alpaca.config.settings import Settings


@pytest.fixture(autouse=True)
def _isolate_settings_from_local_environment(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Keep a developer's ``.env`` file and ``DWARF_ALPACA_*`` variables out of tests.

    Without this, a local ``.env`` (for example one enabling continuous sessions or
    setting the site location and DWARF IP) changes ``Settings()`` defaults and makes
    tests talk to real hardware or fail.

    Physical-device tests (``test_hardware_*``) are configured through those
    variables on purpose, so they are left untouched.
    """

    if request.node.path.name.startswith("test_hardware_"):
        return
    for name in list(os.environ):
        if name.upper().startswith("DWARF_ALPACA_"):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setitem(Settings.model_config, "env_file", None)
