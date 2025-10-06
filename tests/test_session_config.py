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


@pytest.mark.asyncio
async def test_ensure_default_filter_prefers_support_params(params_config: dict[str, object]) -> None:
    session = DwarfSession(Settings())
    session.simulation = False
    session._params_config = params_config
    session.camera_state.filter_name = ""

    taken: dict[str, object] = {}

    async def fake_set_feature_param(self, feature, *, mode_index: int, index: int, continue_value: float = 0.0) -> None:  # type: ignore[override]
        taken["feature_name"] = feature.get("name")
        taken["mode_index"] = mode_index
        taken["index"] = index
        taken["continue_value"] = continue_value

    session._set_feature_param = types.MethodType(fake_set_feature_param, session)

    await session._ensure_default_filter("VIS")

    assert taken["feature_name"] == "IR Cut"
    assert taken["mode_index"] == 0
    assert taken["index"] == 0
    assert taken["continue_value"] == 0.0
    assert session.camera_state.filter_name == "VIS Filter"
