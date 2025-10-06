import types

import pytest

from dwarf_alpaca.config.settings import Settings
from dwarf_alpaca.dwarf.exposure import ExposureOption, ExposureResolver, flatten_exposure_entries
from dwarf_alpaca.dwarf.session import DwarfSession


def test_exposure_resolver_parses_nested_config():
    config = {
        "entries": [
            {"index": "3", "duration": "1/4s"},
            {"index": 7, "time": "0.5 s"},
            {
                "group": {
                    "index": 3,
                    "text": "2 seconds",
                }
            },
        ],
        "metadata": {
            "options": [
                {"index": 1, "value": "15ms"},
                {"index": 2, "exptime": 1},
            ]
        },
    }

    resolver = ExposureResolver.from_config(config)
    assert resolver is not None

    durations = resolver.available_durations()
    assert durations == pytest.approx([0.015, 0.25, 0.5, 1.0])

    assert resolver.choose_index(0.3) == 3
    assert resolver.choose_index(0.02) == 1
    assert resolver.choose_index(0.8) == 2

    flat_entries = flatten_exposure_entries(config)
    assert (3, pytest.approx(0.25)) in flat_entries
    assert (1, pytest.approx(0.015)) in flat_entries


def test_exposure_resolver_ignores_invalid_entries():
    config = {
        "items": [
            {"index": "abc", "duration": "1/10s"},
            {"index": 4, "duration": "0s"},
            {"index": 5, "duration": -1},
            {"index": 6, "duration": ""},
            {"duration": "1s"},
        ]
    }

    resolver = ExposureResolver.from_config(config)
    assert resolver is None

    flat_entries = flatten_exposure_entries(config)
    # Only the valid fractional entry should survive despite invalid index
    assert not flat_entries

    # choose_index should gracefully handle empty resolver
    empty_resolver = ExposureResolver([])
    assert empty_resolver.choose_index(1.0) is None
    assert not empty_resolver


@pytest.mark.asyncio
async def test_session_ensure_exposure_settings_uses_resolver():
    settings = Settings(force_simulation=True)
    session = DwarfSession(settings)
    session.simulation = False
    session._exposure_resolver = ExposureResolver(
        [
            ExposureOption(index=10, seconds=1.0),
            ExposureOption(index=4, seconds=0.2),
        ]
    )

    calls: list[tuple[str, int | None]] = []

    async def fake_mode(self) -> None:
        calls.append(("mode", None))

    async def fake_index(self, idx: int) -> None:
        calls.append(("index", idx))

    session._set_exposure_mode_manual = types.MethodType(fake_mode, session)
    session._set_exposure_index = types.MethodType(fake_index, session)

    await session._ensure_exposure_settings(0.25)

    assert calls == [("mode", None), ("index", 4)]


DWARF_SAMPLE_PAYLOAD = {
    "code": 0,
    "data": {
        "cameras": [
            {
                "id": 0,
                "name": "Tele",
                "supportParams": [
                    {
                        "name": "Exposure",
                        "gearMode": {
                            "values": [
                                {"index": 0, "name": "1/10000"},
                                {"index": 75, "name": "1/30"},
                                {"index": 111, "name": "0.5"},
                                {"index": 120, "name": "1"},
                                {"index": 150, "name": "10"},
                                {"index": 165, "name": "120"},
                            ]
                        },
                    },
                    {
                        "name": "Gain",
                        "gearMode": {
                            "values": [
                                {"index": 0, "name": "0"},
                                {"index": 1, "name": "2"},
                                {"index": 2, "name": "5"},
                            ]
                        },
                    },
                ],
            },
            {
                "id": 1,
                "name": "Wide",
                "supportParams": [
                    {
                        "name": "Exposure",
                        "gearMode": {
                            "values": [
                                {"index": 0, "name": "1/8000"},
                                {"index": 90, "name": "1/10"},
                            ]
                        },
                    }
                ],
            },
        ]
    },
}


def test_exposure_resolver_prefers_tele_camera_from_dwarf_payload():
    resolver = ExposureResolver.from_config(DWARF_SAMPLE_PAYLOAD)
    assert resolver is not None

    durations = resolver.available_durations()
    assert durations == sorted(durations)
    assert pytest.approx(durations[0], rel=1e-6) == 0.0001  # 1/10000
    assert pytest.approx(durations[-1], rel=1e-6) == 120.0

    # Ensure tele camera entries are chosen over wide camera or gain values
    indices = {option.index for option in resolver.options}
    assert indices == {0, 75, 111, 120, 150, 165}

    # Spot check mapping accuracy
    assert resolver.choose_index(0.034) == 75  # closest to 1/30
    assert resolver.choose_index(0.6) == 111
    assert resolver.choose_index(30.0) == 150

    flattened = flatten_exposure_entries(DWARF_SAMPLE_PAYLOAD)
    assert set(index for index, _ in flattened) == indices
