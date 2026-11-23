import json

import pytest

from dwarf_alpaca.gui.activity import (
    DELETE,
    ERROR,
    OK,
    STOP,
    WARN,
    ActivityTranslator,
    parse_record,
)


def _js(event: str, **fields) -> str:
    return json.dumps({"event": event, **fields})


def _texts(entries):
    return [entry.text for entry in entries]


def test_parse_structlog_json_and_key_value_lines() -> None:
    assert parse_record(_js("dwarf.battery.notification", battery_percent=90)) == (
        "dwarf.battery.notification",
        {"battery_percent": 90},
    )
    assert parse_record("cli.start.profile model=dwarf3 ws_client_id=X") == (
        "cli.start.profile",
        {"model": "dwarf3", "ws_client_id": "X"},
    )
    event, fields = parse_record(
        _js(
            "dwarf.system.master_lock_acquired ip=%s mode=%s lock=%s",
            positional_args=["192.168.88.1", 0, True],
        )
    )
    assert event == "dwarf.system.master_lock_acquired"


def test_continuous_sequence_reads_like_a_story() -> None:
    tr = ActivityTranslator()
    tr.configure(model="dwarf3", ip="192.168.88.1")
    feed = []
    feed += tr.feed(_js("dwarf.system.master_lock_acquired", positional_args=["192.168.88.1"]), 0)
    feed += tr.feed(_js("dwarf.system.master_lock_unlocked"), 0.1)
    feed += tr.feed(_js("dwarf.system.master_lock_acquired", positional_args=["192.168.88.1"]), 0.2)
    feed += tr.feed(_js("filterwheel.position_set", filter="Astro Filter"), 1)
    feed += tr.feed(_js("alpaca.camera.start_exposure_request", resolved_duration=30.0, resolved_light=True), 2)
    feed += tr.feed(_js("dwarf.camera.continuous_session_started", device_frames=999), 3)
    feed += tr.feed(_js("dwarf.camera.frame_stored", width=3856, height=2180), 49)
    feed += tr.feed(_js("dwarf.camera.continuous_frame_delivered", frames_delivered=1, frame_end=38.0), 49)
    feed += tr.feed(_js("dwarf.camera.continuous_frame_skipped", path="x"), 60)
    feed += tr.feed(_js("dwarf.camera.continuous_session_ended", reason="camera_disconnect", frames_delivered=1), 100)
    feed += tr.feed(_js("dwarf.camera.astro_capture_state", state_name="stopping"), 100)
    feed += tr.feed(_js("dwarf.camera.astro_capture_state", state_name="stopped"), 140)
    feed += tr.feed(_js("dwarf.camera.astro_cleanup_deleted", folder="DWARF_RAW_X", still_present=False), 142)

    assert _texts(feed) == [
        "Connected to DWARF 3 at 192.168.88.1",
        "Filter: Astro",
        "NINA requested a 30 s light exposure",
        "Continuous DWARF session started",
        "Frame 1 delivered to NINA (3856×2180) · 11 s after the exposure ended",
        "Frame skipped: it finished before NINA asked (Wi-Fi download slower than the "
        "exposures); it stays on the DWARF",
        "Continuous session ended: NINA disconnected the camera (1 frame delivered)",
        "DWARF finished closing the session (40 s)",
        "Session deleted from the DWARF: DWARF_RAW_X",
    ]
    kinds = [entry.kind for entry in feed]
    assert kinds[-1] == DELETE and STOP in kinds and WARN in kinds and kinds[0] == OK


def test_status_line_tracks_connection_camera_and_session() -> None:
    tr = ActivityTranslator()
    tr.configure(model="dwarf3", ip="192.168.88.1")
    tr.feed(_js("dwarf.system.master_lock_acquired", positional_args=["192.168.88.1"]), 0)
    tr.feed(_js("dwarf.battery.notification", battery_percent=100), 0)
    tr.feed(_js("filterwheel.position_set", filter="Duo-Band Filter"), 0)
    tr.feed(_js("alpaca.camera.start_exposure_request", resolved_duration=60.0), 0)
    tr.feed(_js("dwarf.camera.continuous_session_started"), 0)
    tr.feed(_js("dwarf.camera.continuous_frame_delivered", frames_delivered=2, frame_end=0), 0)
    assert tr.status.render() == (
        "DWARF 3 · connected (192.168.88.1)  |  Camera: frame ready  |  "
        "Continuous session: 2 frames  |  Filter: Duo-Band  |  Battery 100 %"
    )


def test_errors_are_explained() -> None:
    tr = ActivityTranslator()
    tr.configure(model="dwarf3", ip="192.168.88.1")
    entries = tr.feed(_js("dwarf.ws.connect_failed", error="timed out"), 0)
    entries += tr.feed(_js("alpaca.camera.gain_rejected", requested=800, minimum=0, maximum=200), 1)
    entries += tr.feed(_js("dwarf.camera.astro_cleanup_skipped", reason="album_entry_not_found"), 2)
    assert [entry.kind for entry in entries] == [ERROR, ERROR, WARN]
    assert "192.168.88.1" in entries[0].text and entries[0].group == "connect_failed"
    assert "800" in entries[1].text and "Default Gain" in entries[1].text
    assert "did not list the session" in entries[2].text
    assert "not responding (192.168.88.1)" in tr.status.render()


@pytest.mark.parametrize(
    "message",
    [
        _js("dwarf.ws.command.send", module_id=1),
        _js("dwarf.camera.capture.trace.packet", command_id=15264),
        "not json at all",
        "{broken json",
    ],
)
def test_technical_noise_is_ignored(message) -> None:
    assert ActivityTranslator().feed(message, 0) == []


def test_low_battery_warns_once() -> None:
    tr = ActivityTranslator()
    first = tr.feed(_js("dwarf.battery.notification", battery_percent=18), 0)
    second = tr.feed(_js("dwarf.battery.notification", battery_percent=17), 1)
    assert len(first) == 1 and first[0].kind == WARN and second == []


def test_telescope_slew_messages() -> None:
    translator = ActivityTranslator()

    connected = translator.feed(_js("alpaca.telescope.connected", simulated=False), 0.0)
    assert _texts(connected) == ["Telescope connected by NINA"]

    request = translator.feed(
        _js("alpaca.telescope.slew_request", ra_hours=20.98, dec_degrees=44.33), 1.0
    )
    assert _texts(request) == ["NINA requested a slew to RA 20.980 h, Dec 44.33°"]

    rejected = translator.feed(
        _js("alpaca.telescope.slew_rejected", reason="telescope not connected"), 2.0
    )
    assert rejected[0].kind == ERROR
    assert "reconnect the telescope" in rejected[0].text


def test_autofocus_not_started_is_a_warning() -> None:
    translator = ActivityTranslator()

    entries = translator.feed(
        _js("dwarf.focus.autofocus.before_calibration.not_started", waited_seconds=20.0),
        0.0,
    )
    entries += translator.feed(
        _js("dwarf.focus.autofocus.before_calibration.skipped", error="x"), 0.1
    )
    assert [entry.kind for entry in entries] == [WARN, WARN]
    assert _texts(entries) == [
        "The DWARF did not start autofocus (waited 20 s)",
        "Continuing without autofocus",
    ]


def test_goto_busy_rejection_message() -> None:
    translator = ActivityTranslator()
    entries = translator.feed(
        _js("dwarf.telescope.goto.one_click.rejected", code=-11501, target_name="M31"), 0.0
    )
    assert entries[0].kind == WARN
    assert "busy" in entries[0].text


def test_status_line_leaves_out_unknown_camera_and_battery() -> None:
    tr = ActivityTranslator()
    tr.configure(model="dwarf3", ip="192.168.88.1")
    assert tr.status.render() == "DWARF 3 · not connected"

    tr.feed(_js("dwarf.system.master_lock_acquired", positional_args=["192.168.88.1"]), 0)
    entries = tr.feed(_js("alpaca.camera.connected"), 1)
    assert _texts(entries) == ["Camera connected by NINA"]
    assert tr.status.render() == "DWARF 3 · connected (192.168.88.1)  |  Camera: idle"


def test_server_stop_resets_status_and_explains() -> None:
    tr = ActivityTranslator()
    tr.configure(model="dwarf3", ip="192.168.88.1")
    tr.feed("INFO uvicorn.error: Uvicorn running on http://192.168.88.2:11111", 0)
    tr.feed(_js("dwarf.system.master_lock_acquired", positional_args=["192.168.88.1"]), 0)
    tr.feed(_js("dwarf.battery.notification", battery_percent=100), 0)
    tr.feed(_js("alpaca.camera.connected"), 0)

    stopped = tr.server_stopped(5.0)
    tr.feed(_js("dwarf.system.master_lock_unlocked", ip="192.168.88.1"), 6.0)

    assert [entry.kind for entry in stopped] == [STOP]
    assert "server stopped" in stopped[0].text
    assert tr.status.render() == "DWARF 3 · not connected"
    assert tr.server_stopped(7.0) == []  # reported once


def test_tracking_stopped_message() -> None:
    tr = ActivityTranslator()
    entries = tr.feed(_js("dwarf.telescope.tracking.stopped"), 0.0)
    entries += tr.feed(
        _js("dwarf.camera.continuous_session_ended", reason="tracking_stopped", frames_delivered=3),
        0.1,
    )
    assert entries[0].kind == STOP
    assert "Tracking stopped by NINA" in entries[0].text
    assert "NINA stopped tracking" in entries[1].text


def test_frames_left_warning() -> None:
    tr = ActivityTranslator()
    kept = tr.feed(_js("dwarf.camera.continuous_frames_left", frames_left=5), 0.0)
    deleted = tr.feed(
        _js("dwarf.camera.continuous_frames_left", frames_left=2, will_be_deleted=True), 1.0
    )
    assert kept[0].kind == WARN
    assert _texts(kept) == [
        "The DWARF took 5 more frame(s) than NINA asked for; they stay on the DWARF"
    ]
    assert "deleted with the session" in deleted[0].text


def test_shared_wait_for_session_close_is_reported_once() -> None:
    tr = ActivityTranslator()
    feed = []
    feed += tr.feed(_js("dwarf.camera.astro_capture_state", state_name="stopping"), 0)
    feed += tr.feed(_js("dwarf.camera.astro_capture_ready_wait_started", state=2, timeout=150), 0)
    feed += tr.feed(_js("dwarf.camera.astro_capture_ready_wait_started", state=2, timeout=150), 0)
    feed += tr.feed(_js("dwarf.camera.astro_capture_state", state_name="stopped"), 38)
    feed += tr.feed(_js("dwarf.camera.astro_capture_ready_wait_finished", elapsed_seconds=38.0), 38)
    feed += tr.feed(_js("dwarf.camera.astro_capture_ready_wait_finished", elapsed_seconds=38.0), 38)

    assert _texts(feed) == [
        "Waiting for the DWARF to close the previous session…",
        "DWARF finished closing the session (38 s)",
    ]


def test_ready_reported_when_close_not_seen() -> None:
    tr = ActivityTranslator()
    feed = tr.feed(_js("dwarf.camera.astro_capture_ready_wait_started", state=2, timeout=150), 0)
    feed += tr.feed(_js("dwarf.camera.astro_capture_ready_wait_finished", elapsed_seconds=12.0), 12)

    assert _texts(feed)[-1] == "DWARF ready after 12 s"


def test_calibration_during_first_goto_and_busy_exposure() -> None:
    tr = ActivityTranslator()
    feed = tr.feed(_js("server.calibration_after_start.awaiting_target", model="dwarf3"), 0)
    feed += tr.feed(_js("dwarf.telescope.calibration.notification.state", state="running"), 10)
    feed += tr.feed(_js("dwarf.telescope.calibration.notification.state", state="plate_solving"), 30)
    feed += tr.feed(_js("dwarf.telescope.calibration.notification.result", outcome="successful"), 52)
    feed += tr.feed(_js("dwarf.camera.astro_capture_busy", code=-11501), 60)

    assert _texts(feed) == [
        "The DWARF will calibrate with the first GOTO from NINA",
        "DWARF calibrating (plate solving the sky)…",
        "DWARF calibrated; the GOTO continues",
        "The DWARF refused the exposure: busy (a GOTO or another session is running)",
    ]


def test_goto_failure_codes_are_explained() -> None:
    tr = ActivityTranslator()
    feed = tr.feed(
        _js("dwarf.telescope.goto.wait_result", result="failed", reason="one_click_code_-11504"), 0
    )
    assert _texts(feed) == [
        "GOTO failed: the DWARF could not calibrate (plate solving found no stars: "
        "daylight, clouds or something in the way)"
    ]


def test_rejected_exposure_settings_are_reported() -> None:
    tr = ActivityTranslator()
    feed = tr.feed(
        _js("dwarf.camera.v3_astro_quick_set_rejected", info_id="0|0|10|60|0|null", code=-3,
            exposure=10.0, gain=60),
        0,
    )
    assert _texts(feed) == [
        "The DWARF rejected 10 s at gain 60 (code -3); the exposure did not start"
    ]


def test_abort_at_nina_camera_timeout_explains_the_timeout() -> None:
    tr = ActivityTranslator()
    tr.feed(_js("alpaca.camera.start_exposure_request", resolved_duration=30.0, resolved_light=True), 0)
    feed = tr.feed(
        _js("dwarf.camera.continuous_session_ended", reason="abort", frames_delivered=0), 90
    )
    texts = _texts(feed)
    assert texts[0] == "Continuous session ended: exposure aborted (0 frames delivered)"
    assert texts[1].startswith("NINA stopped waiting 90 s after asking for the frame")


def test_user_abort_has_no_timeout_hint() -> None:
    tr = ActivityTranslator()
    tr.feed(_js("alpaca.camera.start_exposure_request", resolved_duration=30.0, resolved_light=True), 0)
    feed = tr.feed(
        _js("dwarf.camera.continuous_session_ended", reason="abort", frames_delivered=0), 22
    )
    assert len(feed) == 1


def test_rejected_exposure_request_is_reported() -> None:
    tr = ActivityTranslator()
    feed = tr.feed(
        _js(
            "alpaca.camera.start_rejected",
            error="No exact firmware exposure value is available for requested duration 20s "
            "(supported: 1, 10, 15, 30)",
        ),
        0,
    )
    assert _texts(feed)[0].startswith(
        "Exposure could not start: No exact firmware exposure value is available for requested duration 20s"
    )


def test_lights_turned_off() -> None:
    tr = ActivityTranslator()
    feed = tr.feed(_js("dwarf.lights.off", light="ring_light"), 0)
    feed += tr.feed(_js("dwarf.lights.off", light="battery_indicator"), 0)
    assert _texts(feed) == ["Ring light turned off", "Battery indicator turned off"]


def test_gain_rounding_is_reported() -> None:
    tr = ActivityTranslator()
    feed = tr.feed(_js("dwarf.camera.gain_rounded", requested=65, used=70), 0)
    assert _texts(feed) == ["Gain 65 is not a DWARF value (40–240 in steps of 10); using 70"]
