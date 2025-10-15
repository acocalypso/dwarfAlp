from __future__ import annotations

import json
import types
from pathlib import Path

import pytest

from dwarf_alpaca.config.settings import Settings
from dwarf_alpaca.dwarf import exposure
from dwarf_alpaca.dwarf.session import DwarfSession


@pytest.fixture()
def params_config() -> dict[str, object]:
    sample_path = Path(__file__).parent / "fixtures" / "params_config_sample.json"
    with sample_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def test_exposure_resolver_chooses_expected_index(params_config: dict[str, object]) -> None:
    resolver = exposure.ExposureResolver.from_config(params_config)
    assert resolver is not None
    assert resolver.choose_index(1.0) == 120
    assert any(abs(value - 1.0) < 1e-9 for value in resolver.available_durations())


def test_format_timezone_label_handles_offsets() -> None:
    session = DwarfSession(Settings())
    assert session._format_timezone_label(0.0) == "UTC"
    assert session._format_timezone_label(2.0) == "UTC+02:00"
    assert session._format_timezone_label(-3.5) == "UTC-03:30"
    assert session._format_timezone_label(5.75) == "UTC+05:45"


@pytest.mark.asyncio
async def test_ensure_default_filter_prefers_support_params(params_config: dict[str, object]) -> None:
    session = DwarfSession(Settings())
    session.simulation = False
    session._params_config = params_config
    session.camera_state.filter_name = ""

    taken: dict[str, object] = {}

    async def fake_set_ir_cut(self, *, value: int) -> None:  # type: ignore[override]
        taken["ircut_value"] = value

    async def fake_set_feature_param(self, *args, **kwargs) -> None:  # type: ignore[override]
        raise AssertionError("_set_feature_param should not be called for IR Cut filters")

    async def fake_ensure_ws(self) -> None:  # type: ignore[override]
        return None

    session._set_ir_cut = types.MethodType(fake_set_ir_cut, session)
    session._set_feature_param = types.MethodType(fake_set_feature_param, session)
    session._ensure_ws = types.MethodType(fake_ensure_ws, session)

    await session._ensure_default_filter("VIS")

    assert taken["ircut_value"] == 0
    assert session.camera_state.filter_name == "VIS Filter"
