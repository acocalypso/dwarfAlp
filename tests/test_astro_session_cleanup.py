import types

import pytest

from dwarf_alpaca.config.settings import Settings
from dwarf_alpaca.dwarf import session as session_module
from dwarf_alpaca.dwarf.session import DwarfSession

FOLDER = "DWARF_RAW_TELE_M31_EXP_10_GAIN_80_2026-11-13-01-02-03-456"


def test_astro_session_folder_requires_dwarf_raw_parent() -> None:
    assert DwarfSession._astro_session_folder(f"/Astronomy/{FOLDER}/frame_0001.fits") == FOLDER
    assert DwarfSession._astro_session_folder("/Astronomy/frame.fits") is None
    assert DwarfSession._astro_session_folder("/Photos/IMG_0001.fits") is None
    assert DwarfSession._astro_session_folder(None) is None


def test_album_entry_matches_exact_folder_only() -> None:
    entry = {"astroImageDetails": {"srcDir": f"/sdcard/DWARF_3/Astronomy/{FOLDER}/"}}
    assert DwarfSession._album_entry_matches_folder(entry, FOLDER)
    assert not DwarfSession._album_entry_matches_folder(entry, FOLDER + "_other")
    assert not DwarfSession._album_entry_matches_folder({}, FOLDER)


class _FakeHttp:
    def __init__(self, entries):
        self.entries = list(entries)
        self.deleted = []

    async def list_album_media_infos(self, media_type=1, *, page_index=0, page_size=1):
        return list(self.entries)

    async def delete_album_media(self, datas):
        self.deleted.append(datas)
        self.entries = [
            e for e in self.entries if e.get("filePath") != datas[0]["filePath"]
        ]
        return {"code": 0}


async def _no_sleep(_seconds):
    return None


@pytest.mark.asyncio
async def test_delete_only_matching_session(monkeypatch) -> None:
    monkeypatch.setattr(session_module.asyncio, "sleep", _no_sleep)
    session = DwarfSession(
        Settings(force_simulation=True, delete_astro_session_after_download=True)
    )
    target = {
        "mediaType": 4,
        "subType": 0,
        "fileName": "stacked.jpg",
        "filePath": f"/Astronomy/{FOLDER}/stacked.jpg",
        "astroImageDetails": {"srcDir": f"/Astronomy/{FOLDER}"},
    }
    other = {
        "mediaType": 4,
        "subType": 0,
        "fileName": "stacked.jpg",
        "filePath": "/Astronomy/DWARF_RAW_TELE_M42_x/stacked.jpg",
        "astroImageDetails": {"srcDir": "/Astronomy/DWARF_RAW_TELE_M42_x"},
    }
    fake = _FakeHttp([other, target])
    session._http_client = fake

    await session._delete_astro_session(FOLDER, capture_id="c1")

    assert fake.deleted == [
        [
            {
                "mediaType": 4,
                "fileName": "stacked.jpg",
                "subType": 0,
                "filePath": f"/Astronomy/{FOLDER}/stacked.jpg",
            }
        ]
    ]
    assert fake.entries == [other]


@pytest.mark.asyncio
async def test_no_delete_when_entry_missing(monkeypatch) -> None:
    monkeypatch.setattr(session_module.asyncio, "sleep", _no_sleep)
    session = DwarfSession(
        Settings(
            force_simulation=True,
            delete_astro_session_after_download=True,
            delete_astro_session_timeout_seconds=0.0,
        )
    )
    clock = iter(range(0, 1000, 10))
    monkeypatch.setattr(session_module.time, "monotonic", lambda: next(clock))
    fake = _FakeHttp([])
    session._http_client = fake

    await session._delete_astro_session(FOLDER)

    assert fake.deleted == []


def test_cleanup_disabled_by_default() -> None:
    assert Settings().delete_astro_session_after_download is False
    session = DwarfSession(Settings(force_simulation=True))
    state = types.SimpleNamespace(
        retrieved_file_path=f"/Astronomy/{FOLDER}/frame.fits", capture_id="c1"
    )
    session._schedule_astro_session_cleanup(state)
    assert not session._astro_cleanup_tasks
