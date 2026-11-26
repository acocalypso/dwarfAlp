import asyncio

import pytest

from dwarf_alpaca.config.settings import Settings
from dwarf_alpaca.dwarf import session as session_module
from dwarf_alpaca.dwarf.ftp_client import FtpPhotoEntry
from dwarf_alpaca.dwarf.session import DwarfSession, _ContinuousAstroSession, _OperationState

FOLDER = "/Astronomy/DWARF_RAW_TELE_EXP_5_GAIN_40_2026-11-13-01-41-46-346"


def _entry(name: str, end: float) -> FtpPhotoEntry:
    return FtpPhotoEntry(directory=FOLDER, name=name, timestamp=end, path=f"{FOLDER}/{name}")


def test_select_delivers_oldest_frame_even_if_it_finished_before_the_request() -> None:
    entries = [_entry("a.fits", 100.0), _entry("b.fits", 106.0), _entry("c.fits", 112.0)]
    chosen = DwarfSession._select_continuous_frame(
        entries, delivered=set(), duration=5.0, valid_after=90.0
    )
    assert chosen is not None and chosen.name == "a.fits"


def test_select_ignores_delivered_and_pre_session_frames() -> None:
    entries = [_entry("old.fits", 60.0), _entry("a.fits", 100.0), _entry("b.fits", 106.0)]
    chosen = DwarfSession._select_continuous_frame(
        entries, delivered={f"{FOLDER}/a.fits"}, duration=5.0, valid_after=90.0
    )
    assert chosen is not None and chosen.name == "b.fits"


def test_select_waits_when_every_frame_was_delivered() -> None:
    chosen = DwarfSession._select_continuous_frame(
        [_entry("a.fits", 100.0)], delivered={f"{FOLDER}/a.fits"}, duration=5.0, valid_after=90.0
    )
    assert chosen is None


def _session(**overrides) -> DwarfSession:
    settings = Settings(
        force_simulation=True,
        dwarf_device_model="dwarf3",
        **overrides,
    )
    session = DwarfSession(settings)
    state = session.camera_state
    state.requested_gain = 40
    state.filter_index = 2
    state.requested_bin = (1, 1)
    return session


def test_dwarf3_light_frames_always_use_continuous_session() -> None:
    session = DwarfSession(Settings(dwarf_device_model="dwarf3"))
    assert session._continuous_session_wanted(light=True, mini_profile=False)
    assert not session._continuous_session_wanted(light=False, mini_profile=False)


@pytest.mark.parametrize("model", ["dwarf2", "dwarfmini"])
def test_other_models_use_continuous_session_too(model: str) -> None:
    session = DwarfSession(Settings(dwarf_device_model=model))
    assert session._continuous_session_wanted(
        light=True, mini_profile=session._is_dwarf_mini()
    )


def test_mini_photo_mode_keeps_single_frame_path() -> None:
    session = DwarfSession(
        Settings(dwarf_device_model="dwarfmini", dwarf_mini_capture_mode="photo")
    )
    assert not session._continuous_session_wanted(light=True, mini_profile=True)


def test_reuse_requires_same_settings_running_device_and_known_folder() -> None:
    session = _session()
    session._continuous = _ContinuousAstroSession(
        key=session._continuous_key(5.0, True), started_at=0.0, first_capture_id="c0"
    )
    session._astro_capture_operation_state = _OperationState.RUNNING
    assert not session._continuous_can_reuse(5.0, True)  # first frame not delivered yet

    session._continuous.folder = FOLDER
    assert session._continuous_can_reuse(5.0, True)
    assert not session._continuous_can_reuse(10.0, True)

    session.camera_state.requested_gain = 80
    assert not session._continuous_can_reuse(5.0, True)
    session.camera_state.requested_gain = 40

    session._astro_capture_operation_state = _OperationState.STOPPING
    assert not session._continuous_can_reuse(5.0, True)


@pytest.mark.asyncio
async def test_end_session_stops_device_and_queues_folder_cleanup() -> None:
    session = _session(delete_astro_session_after_download=True)
    session._continuous = _ContinuousAstroSession(
        key=session._continuous_key(5.0, True),
        started_at=0.0,
        first_capture_id="c0",
        folder=FOLDER,
    )
    session._astro_capture_operation_state = _OperationState.RUNNING
    stops: list[bool] = []
    cleanups: list[str] = []

    async def fake_stop(*, strict: bool = False) -> None:
        stops.append(strict)

    session._stop_astro_capture = fake_stop  # type: ignore[method-assign]
    session._schedule_astro_folder_cleanup = (  # type: ignore[method-assign]
        lambda folder, capture_id=None: cleanups.append(folder)
    )

    await session._end_continuous_session(reason="test")

    assert session._continuous is None
    assert stops == [False]
    assert cleanups == [FOLDER.rsplit("/", 1)[-1]]
    assert session._last_continuous_folder == FOLDER
    await asyncio.sleep(0)
    if session._background_go_live_task is not None:
        session._background_go_live_task.cancel()


@pytest.mark.asyncio
async def test_live_view_restored_after_continuous_session_stops() -> None:
    session = _session()
    session.simulation = False
    session._continuous = _ContinuousAstroSession(
        key=session._continuous_key(5.0, True),
        started_at=0.0,
        first_capture_id="c0",
        folder=FOLDER,
    )
    session._astro_capture_operation_state = _OperationState.RUNNING
    calls: list[str] = []

    async def fake_stop(*, strict: bool = False) -> None:
        calls.append("stop")

    async def fake_wait(*, timeout=None) -> None:
        calls.append("wait")

    async def fake_go_live() -> None:
        calls.append("go_live")

    session._stop_astro_capture = fake_stop  # type: ignore[method-assign]
    session._wait_for_astro_capture_ready = fake_wait  # type: ignore[method-assign]
    session._astro_go_live = fake_go_live  # type: ignore[method-assign]
    session._schedule_astro_folder_cleanup = (  # type: ignore[method-assign]
        lambda folder, capture_id=None: None
    )

    async def fake_report(cont, *, wait_for_stop, after=None) -> None:
        if after is not None:
            await asyncio.wait({after})
        calls.append("report")

    session._report_frames_left_on_device = fake_report  # type: ignore[method-assign]

    await session._end_continuous_session(reason="idle_timeout")
    await session._background_go_live_task
    await session._frames_left_task

    assert calls == ["stop", "wait", "go_live", "report"]


@pytest.mark.asyncio
async def test_deferred_start_runs_after_device_is_ready() -> None:
    session = _session()
    calls: list[str] = []

    async def fake_wait(*, timeout=None) -> None:
        calls.append("wait")

    async def fake_start(duration, light, **kwargs) -> None:
        calls.append("start")
        assert kwargs["reuse_continuous"] is False

    session._wait_for_astro_capture_ready = fake_wait  # type: ignore[method-assign]
    session._camera_start_exposure_ready = fake_start  # type: ignore[method-assign]
    session._defer_start_until_ready(
        10.0, True, continue_without_darks=None, mini_profile=False, continuous_wanted=False
    )
    assert session.camera_state.capture_phase.value == "configuring"
    await session.camera_state.capture_task
    assert calls == ["wait", "start"]


@pytest.mark.asyncio
async def test_deferred_start_failure_marks_capture_failed() -> None:
    session = _session()

    async def fake_wait(*, timeout=None) -> None:
        raise RuntimeError("still busy")

    session._wait_for_astro_capture_ready = fake_wait  # type: ignore[method-assign]
    session._defer_start_until_ready(
        10.0, True, continue_without_darks=None, mini_profile=False, continuous_wanted=False
    )
    await session.camera_state.capture_task
    assert session.camera_state.capture_phase.value == "failed"
    assert "still busy" in (session.camera_state.last_error or "")


@pytest.mark.asyncio
async def test_deferred_start_skipped_after_abort() -> None:
    session = _session()
    started: list[bool] = []

    async def fake_wait(*, timeout=None) -> None:
        session.camera_state.capture_id = None  # abort happened meanwhile

    async def fake_start(duration, light, **kwargs) -> None:
        started.append(True)

    session._wait_for_astro_capture_ready = fake_wait  # type: ignore[method-assign]
    session._camera_start_exposure_ready = fake_start  # type: ignore[method-assign]
    session._defer_start_until_ready(
        10.0, True, continue_without_darks=None, mini_profile=False, continuous_wanted=False
    )
    await session.camera_state.capture_task
    assert started == []


def test_failed_rename_is_the_same_frame() -> None:
    # Delivered as "a.fits", later renamed by the firmware to "failed_a.fits".
    entries = [_entry("failed_a.fits", 100.0), _entry("b.fits", 130.0)]
    delivered = {f"{FOLDER}/a.fits"}
    chosen = DwarfSession._select_continuous_frame(
        entries, delivered=delivered, duration=30.0, valid_after=60.0
    )
    assert chosen is not None and chosen.name == "b.fits"


def test_rename_in_progress_yields_one_candidate() -> None:
    entries = [_entry("a.fits", 100.0), _entry("failed_a.fits", 100.0)]
    chosen = DwarfSession._select_continuous_frame(
        entries, delivered=set(), duration=30.0, valid_after=60.0
    )
    assert chosen is not None and chosen.name == "failed_a.fits"
    assert DwarfSession._continuous_frame_key(entries[0]) == DwarfSession._continuous_frame_key(
        entries[1]
    )


@pytest.mark.asyncio
async def test_frames_left_on_device_are_reported(monkeypatch) -> None:
    session = _session()
    session.simulation = False
    cont = _ContinuousAstroSession(
        key=session._continuous_key(10.0, True),
        started_at=0.0,
        first_capture_id="c0",
        folder=FOLDER,
    )
    cont.delivered = {f"{FOLDER}/a.fits"}
    cont.frames_delivered = 1

    async def fake_list(_folder):
        return [_entry("a.fits", 10.0), _entry("b.fits", 20.0), _entry("failed_c.fits", 30.0)]

    class FakeFtp:
        list_astro_raw_fits = staticmethod(fake_list)

    monkeypatch.setattr(session, "_ftp_client", FakeFtp())
    logged: list[dict] = []
    monkeypatch.setattr(
        session_module.logger,
        "warning",
        lambda event, **fields: logged.append({"event": event, **fields}),
    )

    await session._report_frames_left_on_device(cont, wait_for_stop=False)

    assert logged == [
        {
            "event": "dwarf.camera.continuous_frames_left",
            "folder": FOLDER,
            "frames_left": 2,
            "frames_delivered": 1,
            "will_be_deleted": False,
        }
    ]


def test_goto_stays_valid_while_tracking() -> None:
    session = _session()
    session._record_goto(0.712, 41.27)
    session._last_goto_time = 0.0  # long ago
    assert session._has_recent_goto()
    session._clear_goto(reason="tracking_stopped")
    assert not session._has_recent_goto()
