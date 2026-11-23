"""Plain-language activity feed built from the technical log.

The technical log (console tab and log file) is left untouched. This module only
*reads* the same records and turns the handful that matter to an observer into
short English sentences plus a one-line status summary. It has no Qt
dependency so it can be tested on its own.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

# Entry kinds, used by the GUI for icon and colour.
OK = "ok"
INFO = "info"
ACTION = "action"
WAIT = "wait"
WARN = "warn"
ERROR = "error"
STOP = "stop"
DELETE = "delete"

ICONS = {
    OK: "✔",
    INFO: "ℹ",
    ACTION: "▶",
    WAIT: "⏳",
    WARN: "⚠",
    ERROR: "✖",
    STOP: "■",
    DELETE: "🗑",
}

COLORS = {
    OK: "#2e7d32",
    INFO: "#455a64",
    ACTION: "#1565c0",
    WAIT: "#b26a00",
    WARN: "#e65100",
    ERROR: "#b00020",
    STOP: "#455a64",
    DELETE: "#6a1b9a",
}

MODEL_NAMES = {"dwarf3": "DWARF 3", "dwarf2": "DWARF 2", "dwarfmini": "DWARF mini"}

SESSION_END_REASONS = {
    "settings_changed_or_not_running": "exposure, gain, filter or binning changed",
    "abort": "exposure aborted",
    "camera_disconnect": "NINA disconnected the camera",
    "telescope_slew": "telescope slew",
    "telescope_move_axis": "telescope moved",
    "focuser_move": "focuser moved",
    "filter_change": "filter changed",
    "idle_timeout": "no new exposure was requested",
    "device_stopped": "the DWARF stopped capturing",
    "frame_timeout": "no new frame arrived in time",
    "shutdown": "the app is closing",
    "tracking_stopped": "NINA stopped tracking",
}

CLEANUP_SKIP_REASONS = {
    "album_entry_not_found": "the DWARF did not list the session in time",
    "album_entry_incomplete": "the album entry was incomplete",
    "no_dwarf_raw_folder": "the capture folder was not recognised",
}

LOW_BATTERY_PERCENT = 20

_KV_RE = re.compile(r"(\w+)=(\S+)")
_UVICORN_RE = re.compile(r"Uvicorn running on \S+?:(\d+)")


@dataclass
class ActivityEntry:
    timestamp: float
    kind: str
    text: str
    # Consecutive entries with the same group are merged by the GUI (×N).
    group: Optional[str] = None


@dataclass
class ActivityStatus:
    model: Optional[str] = None
    ip: Optional[str] = None
    connection: str = "not connected"
    # None means "not known": the item is left out of the status line.
    camera: Optional[str] = None
    session_frames: Optional[int] = None
    filter_name: Optional[str] = None
    telescope: Optional[str] = None
    battery: Optional[int] = None

    def render(self) -> str:
        device = MODEL_NAMES.get(self.model or "", "DWARF")
        connection = self.connection
        if self.ip and self.connection in {"connected", "not responding"}:
            connection = f"{self.connection} ({self.ip})"
        parts = [f"{device} · {connection}"]
        if self.camera:
            parts.append(f"Camera: {self.camera}")
        if self.session_frames is not None:
            noun = "frame" if self.session_frames == 1 else "frames"
            parts.append(f"Continuous session: {self.session_frames} {noun}")
        if self.filter_name:
            parts.append(f"Filter: {self.filter_name}")
        if self.telescope:
            parts.append(f"Telescope: {self.telescope}")
        if self.battery is not None:
            parts.append(f"Battery {self.battery} %")
        return "  |  ".join(parts)


def _num(value: Any, digits: int = 0) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if digits == 0:
        return f"{number:.0f}" if number >= 10 or number.is_integer() else f"{number:g}"
    return f"{number:.{digits}f}"


def _seconds(value: Any) -> str:
    try:
        return f"{float(value):.0f}"
    except (TypeError, ValueError):
        return str(value)


def _short_filter(name: Any) -> Optional[str]:
    if not isinstance(name, str) or not name.strip():
        return None
    return name.replace(" Filter", "").strip()


def parse_record(message: str) -> tuple[Optional[str], dict[str, Any]]:
    """Return (event, fields) for a structlog JSON line or a ``name k=v`` line."""

    text = message.strip()
    if text.startswith("{"):
        try:
            data = json.loads(text)
        except ValueError:
            return None, {}
        if isinstance(data, dict):
            event = str(data.pop("event", "") or "")
            # Some events are logged printf-style: "name ip=%s mode=%s".
            if " " in event:
                event = event.split(" ", 1)[0]
            return event or None, data
        return None, {}
    head, _, rest = text.partition(" ")
    return head or None, dict(_KV_RE.findall(rest))


# DWARF result codes and dwarfAlp reasons seen when a GOTO fails, in words.
_GOTO_FAILURE_TEXT = {
    "-11504": (
        "the DWARF could not calibrate (plate solving found no stars: daylight, "
        "clouds or something in the way)"
    ),
    "-11501": "the DWARF was busy with another task",
    "goto_idle": "the DWARF did not start moving",
}


class ActivityTranslator:
    """Turn log records into activity entries and keep the status line."""

    def __init__(self) -> None:
        self.status = ActivityStatus()
        self._last_size: Optional[tuple[int, int]] = None
        self._continuous = False
        self._stopping_since: Optional[float] = None
        # A GOTO and the return to live view can wait for the same session
        # close at once; report that wait and its end only once.
        self._ready_wait_open = False
        self._session_closed_at: Optional[float] = None
        self._last_exposure_request: Optional[tuple[float, Optional[float]]] = None
        self._goto_warning_shown = False
        self._low_battery_warned = False
        self._released_at: Optional[float] = None
        self._server_running = False
        self._handlers: dict[str, Callable[[dict[str, Any], float], list[ActivityEntry]]] = {
            "cli.start.profile": self._on_profile,
            "cli.start.connected": self._on_cli_connected,
            "server.starting": self._on_server_starting,
            "server.stopped": self._on_server_stopped,
            "dwarf.system.master_lock_acquired": self._on_lock_acquired,
            "dwarf.system.master_lock_unlocked": self._on_lock_released,
            "dwarf.ws.connect_failed": self._on_connect_failed,
            "alpaca.camera.connected": self._on_camera_connect,
            "alpaca.camera.disconnected": self._on_camera_disconnect,
            "filterwheel.position_set": self._on_filter,
            "filterwheel.initialize_position": self._on_filter,
            "alpaca.camera.start_exposure_request": self._on_exposure_request,
            "alpaca.camera.gain_rejected": self._on_gain_rejected,
            "dwarf.camera.v3_astro_params_applied": self._on_params_applied,
            "dwarf.camera.start_deferred_until_ready": self._on_ready_wait,
            "dwarf.camera.astro_capture_ready_wait_started": self._on_ready_wait,
            "dwarf.camera.astro_capture_ready_wait_finished": self._on_ready_done,
            "dwarf.camera.astro_capture_ready_wait_timeout": self._on_ready_timeout,
            "dwarf.camera.deferred_start_failed": self._on_start_failed,
            "alpaca.camera.start_rejected": self._on_start_failed,
            "dwarf.lights.off": self._on_light_off,
            "dwarf.camera.gain_rounded": self._on_gain_rounded,
            "dwarf.lights.off_failed": self._on_light_off_failed,
            "dwarf.camera.v3_astro_quick_set_rejected": self._on_quick_set_rejected,
            "dwarf.camera.astro_capture_state": self._on_capture_state,
            "dwarf.camera.astro_capture_goto_missing": self._on_goto_missing,
            "dwarf.camera.dark_library_missing_continuing": self._on_no_darks,
            "dwarf.camera.continuous_session_started": self._on_session_started,
            "dwarf.camera.continuous_frame_delivered": self._on_continuous_frame,
            "dwarf.camera.continuous_frames_left": self._on_frames_left,
            "dwarf.camera.continuous_frame_skipped": self._on_frame_skipped,
            "dwarf.camera.continuous_frame_failed": self._on_frame_failed,
            "dwarf.camera.continuous_session_ended": self._on_session_ended,
            "dwarf.camera.frame_stored": self._on_frame_stored,
            "dwarf.camera.astro_cleanup_deleted": self._on_cleanup_deleted,
            "dwarf.camera.astro_cleanup_skipped": self._on_cleanup_skipped,
            "dwarf.camera.astro_cleanup_failed": self._on_cleanup_failed,
            "dwarf.telescope.goto.one_click.starting": self._on_goto_start,
            "dwarf.telescope.goto.retrying": self._on_goto_retry,
            "dwarf.telescope.goto.waiting_for_capture_stop": self._on_goto_waits_for_capture,
            "dwarf.telescope.goto.one_click.rejected": self._on_goto_rejected,
            "dwarf.camera.go_live_after_session": self._on_live_view_restored,
            "dwarf.telescope.goto.wait_result": self._on_goto_result,
            "dwarf.telescope.goto.wait_timeout": self._on_goto_timeout,
            "dwarf.telescope.goto.timeout": self._on_goto_timeout,
            "dwarf.telescope.calibration.starting": self._on_calibration_start,
            "dwarf.telescope.calibration.completed": self._on_calibration_done,
            "dwarf.telescope.calibration.outcome": self._on_calibration_outcome,
            "dwarf.tracking.notification.state": self._on_tracking,
            "dwarf.focus.move.completed": self._on_focus_moved,
            "dwarf.focus.autofocus.before_calibration.starting": self._on_autofocus_start,
            "dwarf.focus.autofocus.before_calibration.completed": self._on_autofocus_done,
            "dwarf.focus.autofocus.before_calibration.failed": self._on_autofocus_failed,
            "dwarf.focus.autofocus.before_calibration.not_started": self._on_autofocus_not_started,
            "dwarf.focus.autofocus.before_calibration.skipped": self._on_autofocus_skipped,
            "server.calibration_after_start.failed": self._on_startup_calibration_failed,
            "server.calibration_after_start.awaiting_target": self._on_calibration_awaiting,
            "dwarf.telescope.calibration.notification.state": self._on_calibration_state,
            "dwarf.telescope.calibration.notification.result": self._on_calibration_result,
            "dwarf.camera.astro_capture_busy": self._on_capture_busy,
            "dwarf.camera.abort_superseded_by_new_exposure": self._on_abort_superseded,
            "dwarf.telescope.abort_slew.stop_not_confirmed": self._on_abort_slew_unconfirmed,
            "alpaca.telescope.connected": self._on_telescope_connected,
            "alpaca.telescope.disconnected": self._on_telescope_disconnected,
            "alpaca.telescope.slew_request": self._on_slew_request,
            "dwarf.telescope.tracking.stopped": self._on_tracking_stopped,
            "alpaca.telescope.slew_rejected": self._on_slew_rejected,
            "alpaca.telescope.slew_failed": self._on_slew_failed,
            "dwarf.battery.notification": self._on_battery,
            "http.request.error": self._on_http_error,
        }

    # region entry point
    def configure(self, *, model: Optional[str], ip: Optional[str]) -> None:
        """Seed the status line from the settings used to start the server."""

        if model:
            self.status.model = model
        if ip:
            self.status.ip = ip

    def server_stopped(self, created: float) -> list[ActivityEntry]:
        """Reset everything that is no longer known once the server has stopped."""

        if not self._server_running:
            return []
        self._server_running = False
        self._released_at = None
        self._continuous = False
        self.status.connection = "not connected"
        self.status.camera = None
        self.status.session_frames = None
        self.status.filter_name = None
        self.status.telescope = None
        self.status.battery = None
        return [
            ActivityEntry(
                created,
                STOP,
                "Alpaca server stopped: the DWARF is released and NINA can no longer "
                "reach it",
            )
        ]

    def feed(self, message: str, created: float) -> list[ActivityEntry]:
        uvicorn = _UVICORN_RE.search(message)
        if uvicorn:
            self._server_running = True
            return [
                ActivityEntry(created, OK, f"Alpaca server running on port {uvicorn.group(1)}")
            ]
        event, fields = parse_record(message)
        if not event:
            return []
        handler = self._handlers.get(event)
        if handler is None:
            return []
        try:
            return handler(fields, created)
        except Exception:  # never let a formatting problem break the GUI
            return []

    # endregion

    # region connection and server
    def _on_profile(self, f: dict[str, Any], t: float) -> list[ActivityEntry]:
        self.status.model = str(f.get("model") or self.status.model or "")
        return []

    def _on_cli_connected(self, f: dict[str, Any], t: float) -> list[ActivityEntry]:
        self.status.ip = f.get("ip") or self.status.ip
        return []

    def _on_server_starting(self, f: dict[str, Any], t: float) -> list[ActivityEntry]:
        return [ActivityEntry(t, INFO, f"Starting Alpaca server on port {f.get('port')}")]

    def _on_server_stopped(self, f: dict[str, Any], t: float) -> list[ActivityEntry]:
        self._server_running = True  # make sure the reset and message happen once
        return self.server_stopped(t)

    def _on_lock_acquired(self, f: dict[str, Any], t: float) -> list[ActivityEntry]:
        args = f.get("positional_args") or []
        ip = f.get("ip") or (args[0] if args else None) or self.status.ip
        self.status.ip = ip
        reconnect = self._released_at is not None and t - self._released_at < 5.0
        already = self.status.connection == "connected"
        self._released_at = None
        self.status.connection = "connected"
        if reconnect or already:
            # Start-up checks and camera reconnects release and re-take control
            # within a second; that is not news for the observer.
            return []
        device = MODEL_NAMES.get(self.status.model or "", "DWARF")
        return [ActivityEntry(t, OK, f"Connected to {device} at {ip}")]

    def _on_lock_released(self, f: dict[str, Any], t: float) -> list[ActivityEntry]:
        self._released_at = t
        # Before the server runs (start-up checks) or after it stopped the DWARF
        # is simply not in use; "released" only makes sense while serving.
        self.status.connection = "released" if self._server_running else "not connected"
        return []

    def _on_connect_failed(self, f: dict[str, Any], t: float) -> list[ActivityEntry]:
        self.status.connection = "not responding"
        self.status.battery = None  # last value is stale while the DWARF is unreachable
        ip = self.status.ip or "the configured IP"
        return [
            ActivityEntry(
                t,
                ERROR,
                f"DWARF not responding at {ip}. Check the IP and that it is on the "
                "same Wi-Fi network",
                group="connect_failed",
            )
        ]

    def _on_camera_connect(self, f: dict[str, Any], t: float) -> list[ActivityEntry]:
        self.status.camera = "idle"
        return [ActivityEntry(t, OK, "Camera connected by NINA")]

    def _on_camera_disconnect(self, f: dict[str, Any], t: float) -> list[ActivityEntry]:
        self.status.camera = "disconnected"
        return [ActivityEntry(t, INFO, "Camera disconnected by NINA")]

    # endregion

    # region camera
    def _on_filter(self, f: dict[str, Any], t: float) -> list[ActivityEntry]:
        name = _short_filter(f.get("filter"))
        if not name or name == self.status.filter_name:
            return []
        self.status.filter_name = name
        return [ActivityEntry(t, INFO, f"Filter: {name}")]

    def _on_exposure_request(self, f: dict[str, Any], t: float) -> list[ActivityEntry]:
        try:
            requested = float(f.get("resolved_duration"))
        except (TypeError, ValueError):
            requested = None
        self._last_exposure_request = (t, requested)
        duration = f.get("resolved_duration")
        light = f.get("resolved_light", True)
        kind = "light" if light in (True, "True", "true", None) else "dark"
        self.status.camera = f"exposing {_num(duration)} s"
        return [ActivityEntry(t, ACTION, f"NINA requested a {_num(duration)} s {kind} exposure")]

    def _on_gain_rejected(self, f: dict[str, Any], t: float) -> list[ActivityEntry]:
        return [
            ActivityEntry(
                t,
                ERROR,
                f"NINA requested gain {f.get('requested')}: out of range "
                f"({f.get('minimum')}–{f.get('maximum')}). Check NINA's Default Gain",
                group="gain_rejected",
            )
        ]

    def _on_params_applied(self, f: dict[str, Any], t: float) -> list[ActivityEntry]:
        return [
            ActivityEntry(
                t, INFO, f"DWARF set to {_num(f.get('exposure'))} s, gain {f.get('gain')}"
            )
        ]

    def _on_ready_wait(self, f: dict[str, Any], t: float) -> list[ActivityEntry]:
        self.status.camera = "waiting for the DWARF"
        if self._ready_wait_open:
            return []
        self._ready_wait_open = True
        return [
            ActivityEntry(
                t,
                WAIT,
                "Waiting for the DWARF to close the previous session…",
                group="ready_wait",
            )
        ]

    def _on_ready_done(self, f: dict[str, Any], t: float) -> list[ActivityEntry]:
        was_open = self._ready_wait_open
        self._ready_wait_open = False
        if not was_open:
            return []
        if self._session_closed_at is not None and t - self._session_closed_at <= 2.0:
            return []  # "DWARF finished closing the session" already said it
        return [ActivityEntry(t, OK, f"DWARF ready after {_seconds(f.get('elapsed_seconds'))} s")]

    def _on_ready_timeout(self, f: dict[str, Any], t: float) -> list[ActivityEntry]:
        self._ready_wait_open = False
        self.status.camera = "DWARF busy"
        return [
            ActivityEntry(t, ERROR, f"DWARF still busy after {_seconds(f.get('timeout'))} s")
        ]

    def _on_gain_rounded(self, f: dict[str, Any], t: float) -> list[ActivityEntry]:
        return [
            ActivityEntry(
                t,
                INFO,
                f"Gain {f.get('requested')} is not a DWARF value (40–240 in steps of 10); "
                f"using {f.get('used')}",
                group="gain_rounded",
            )
        ]

    def _on_light_off(self, f: dict[str, Any], t: float) -> list[ActivityEntry]:
        name = "Ring light" if f.get("light") == "ring_light" else "Battery indicator"
        return [ActivityEntry(t, INFO, f"{name} turned off")]

    def _on_light_off_failed(self, f: dict[str, Any], t: float) -> list[ActivityEntry]:
        name = "ring light" if f.get("light") == "ring_light" else "battery indicator"
        return [ActivityEntry(t, WARN, f"Could not turn the {name} off: {f.get('error')}")]

    def _on_quick_set_rejected(self, f: dict[str, Any], t: float) -> list[ActivityEntry]:
        self.status.camera = "failed"
        return [
            ActivityEntry(
                t,
                ERROR,
                f"The DWARF rejected {_seconds(f.get('exposure'))} s at gain {f.get('gain')} "
                f"(code {f.get('code')}); the exposure did not start",
                group="quick_set_rejected",
            )
        ]

    def _on_start_failed(self, f: dict[str, Any], t: float) -> list[ActivityEntry]:
        if "quick-set" in str(f.get("error", "")):
            return []  # already reported with the exposure and gain
        self.status.camera = "failed"
        return [ActivityEntry(t, ERROR, f"Exposure could not start: {f.get('error')}")]

    def _on_capture_state(self, f: dict[str, Any], t: float) -> list[ActivityEntry]:
        name = f.get("state_name")
        if name == "stopping":
            if self._stopping_since is None:
                self._stopping_since = t
            return []
        if name == "stopped" and self._stopping_since is not None:
            elapsed = t - self._stopping_since
            self._stopping_since = None
            self._session_closed_at = t
            return [ActivityEntry(t, OK, f"DWARF finished closing the session ({elapsed:.0f} s)")]
        if name in {"running", "idle"}:
            self._stopping_since = None
        return []

    def _on_goto_missing(self, f: dict[str, Any], t: float) -> list[ActivityEntry]:
        if self._goto_warning_shown:
            return []
        self._goto_warning_shown = True
        return [
            ActivityEntry(
                t,
                INFO,
                "No GOTO from NINA in this session: the DWARF images wherever it points",
            )
        ]

    def _on_no_darks(self, f: dict[str, Any], t: float) -> list[ActivityEntry]:
        return [
            ActivityEntry(
                t,
                WARN,
                "No dark library for these settings: continuing without darks",
                group="no_darks",
            )
        ]

    def _on_session_started(self, f: dict[str, Any], t: float) -> list[ActivityEntry]:
        self._continuous = True
        self.status.session_frames = 0
        return [ActivityEntry(t, OK, "Continuous DWARF session started")]

    def _on_frame_stored(self, f: dict[str, Any], t: float) -> list[ActivityEntry]:
        try:
            self._last_size = (int(f.get("width")), int(f.get("height")))
        except (TypeError, ValueError):
            self._last_size = None
        if self._continuous:
            return []  # reported by continuous_frame_delivered
        self.status.camera = "frame ready"
        size = f" ({self._last_size[0]}×{self._last_size[1]})" if self._last_size else ""
        return [ActivityEntry(t, OK, f"Frame delivered to NINA{size}")]

    def _on_continuous_frame(self, f: dict[str, Any], t: float) -> list[ActivityEntry]:
        number = int(f.get("frames_delivered") or 0)
        self.status.session_frames = number
        self.status.camera = "frame ready"
        size = ""
        if number == 1 and self._last_size:
            size = f" ({self._last_size[0]}×{self._last_size[1]})"
        delay = ""
        try:
            delay = f" · {max(0.0, t - float(f.get('frame_end'))):.0f} s after the exposure ended"
        except (TypeError, ValueError):
            pass
        if f.get("stacking_failed"):
            return [
                ActivityEntry(
                    t,
                    WARN,
                    f"Frame {number} delivered to NINA{size}{delay} · the DWARF could not "
                    "stack it (few stars, clouds or trailing?)",
                )
            ]
        return [ActivityEntry(t, OK, f"Frame {number} delivered to NINA{size}{delay}")]

    def _on_frame_skipped(self, f: dict[str, Any], t: float) -> list[ActivityEntry]:
        return [
            ActivityEntry(
                t,
                WARN,
                "Frame skipped: it finished before NINA asked (Wi-Fi download slower "
                "than the exposures); it stays on the DWARF",
                group="frame_skipped",
            )
        ]

    def _on_frame_failed(self, f: dict[str, Any], t: float) -> list[ActivityEntry]:
        self.status.camera = "failed"
        reason = SESSION_END_REASONS.get(str(f.get("reason")), str(f.get("reason")))
        return [ActivityEntry(t, ERROR, f"No frame from the DWARF: {reason}")]

    def _on_session_ended(self, f: dict[str, Any], t: float) -> list[ActivityEntry]:
        self._continuous = False
        self.status.session_frames = None
        reason = SESSION_END_REASONS.get(str(f.get("reason")), str(f.get("reason")))
        delivered = f.get("frames_delivered", 0)
        noun = "frame" if delivered == 1 else "frames"
        entries = [
            ActivityEntry(
                t, STOP, f"Continuous session ended: {reason} ({delivered} {noun} delivered)"
            )
        ]
        request = self._last_exposure_request
        if f.get("reason") == "abort" and request is not None and request[1] is not None:
            waited = t - request[0]
            # Sky test 2026-11-20: NINA aborted 90 s after asking for a 30 s
            # frame, i.e. at its 60 s camera timeout, while the DWARF was
            # still closing the previous session and starting the next.
            if waited >= request[1] + 55.0:
                entries.append(
                    ActivityEntry(
                        t,
                        WARN,
                        f"NINA stopped waiting {_seconds(waited)} s after asking for the frame "
                        "(its camera timeout). The first frame of a DWARF session can take "
                        "1–2 minutes more than the exposure: set Options → Equipment → Camera → "
                        "Camera Timeout to 180 s in NINA",
                    )
                )
        return entries

    def _on_cleanup_deleted(self, f: dict[str, Any], t: float) -> list[ActivityEntry]:
        if f.get("still_present"):
            return [
                ActivityEntry(
                    t, WARN, "The DWARF accepted the deletion but still lists the session"
                )
            ]
        return [ActivityEntry(t, DELETE, f"Session deleted from the DWARF: {f.get('folder')}")]

    def _on_cleanup_skipped(self, f: dict[str, Any], t: float) -> list[ActivityEntry]:
        reason = CLEANUP_SKIP_REASONS.get(str(f.get("reason")), str(f.get("reason")))
        return [ActivityEntry(t, WARN, f"Session not deleted: {reason}")]

    def _on_cleanup_failed(self, f: dict[str, Any], t: float) -> list[ActivityEntry]:
        return [ActivityEntry(t, ERROR, f"Deleting the session failed: {f.get('error')}")]

    # endregion

    # region telescope and focuser
    def _on_goto_start(self, f: dict[str, Any], t: float) -> list[ActivityEntry]:
        self._goto_warning_shown = False
        self.status.telescope = "slewing"
        target = f.get("target_name")
        if not target:
            target = f"RA {_num(f.get('ra_hours'), 3)} h, Dec {_num(f.get('dec_degrees'), 2)}°"
        return [
            ActivityEntry(
                t, ACTION, f"GOTO to {target} (the DWARF may calibrate first; this can take minutes)"
            )
        ]

    def _on_goto_retry(self, f: dict[str, Any], t: float) -> list[ActivityEntry]:
        return [ActivityEntry(t, WARN, f"GOTO retrying (DWARF code {f.get('code')})", group="goto_retry")]

    def _on_frames_left(self, f: dict[str, Any], t: float) -> list[ActivityEntry]:
        left = f.get("frames_left")
        where = (
            "they will be deleted with the session"
            if f.get("will_be_deleted")
            else "they stay on the DWARF"
        )
        return [
            ActivityEntry(
                t, WARN, f"The DWARF took {left} more frame(s) than NINA asked for; {where}"
            )
        ]

    def _on_goto_waits_for_capture(self, f: dict[str, Any], t: float) -> list[ActivityEntry]:
        return [
            ActivityEntry(
                t, WAIT, "GOTO waits until the DWARF finishes closing the capture session"
            )
        ]

    def _on_live_view_restored(self, f: dict[str, Any], t: float) -> list[ActivityEntry]:
        return [ActivityEntry(t, INFO, "DWARF back to live view")]

    def _on_goto_rejected(self, f: dict[str, Any], t: float) -> list[ActivityEntry]:
        code = f.get("code")
        if str(code) == "-11501":
            text = "DWARF busy: stopping the previous target before retrying the GOTO"
            return [ActivityEntry(t, WARN, text)]
        return [ActivityEntry(t, WARN, f"DWARF rejected the GOTO (code {code})")]

    def _on_goto_result(self, f: dict[str, Any], t: float) -> list[ActivityEntry]:
        if f.get("result") == "success":
            self.status.telescope = "tracking"
            return [ActivityEntry(t, OK, "GOTO completed: tracking the target")]
        self.status.telescope = "GOTO failed"
        reason = str(f.get("reason") or f.get("result"))
        explained = _GOTO_FAILURE_TEXT.get(reason)
        if explained is None and reason.startswith("one_click_code_"):
            explained = _GOTO_FAILURE_TEXT.get(reason[len("one_click_code_"):])
        if explained:
            return [ActivityEntry(t, ERROR, f"GOTO failed: {explained}")]
        return [ActivityEntry(t, ERROR, f"GOTO failed: {reason}")]

    def _on_goto_timeout(self, f: dict[str, Any], t: float) -> list[ActivityEntry]:
        self.status.telescope = "GOTO timed out"
        return [ActivityEntry(t, ERROR, "GOTO timed out", group="goto_timeout")]

    def _on_calibration_start(self, f: dict[str, Any], t: float) -> list[ActivityEntry]:
        self.status.telescope = "calibrating"
        return [ActivityEntry(t, WAIT, "Calibrating (plate solving)…")]

    def _on_calibration_awaiting(self, f: dict[str, Any], t: float) -> list[ActivityEntry]:
        return [ActivityEntry(t, INFO, "The DWARF will calibrate with the first GOTO from NINA")]

    def _on_calibration_state(self, f: dict[str, Any], t: float) -> list[ActivityEntry]:
        if f.get("state") != "running" or self.status.telescope == "calibrating":
            return []
        self.status.telescope = "calibrating"
        return [
            ActivityEntry(t, WAIT, "DWARF calibrating (plate solving the sky)…", group="calibration")
        ]

    def _on_calibration_result(self, f: dict[str, Any], t: float) -> list[ActivityEntry]:
        if f.get("outcome") == "successful":
            return [ActivityEntry(t, OK, "DWARF calibrated; the GOTO continues")]
        self.status.telescope = "calibration failed"
        return [ActivityEntry(t, ERROR, f"DWARF calibration failed ({f.get('outcome')})")]

    def _on_capture_busy(self, f: dict[str, Any], t: float) -> list[ActivityEntry]:
        self.status.camera = "DWARF busy"
        return [
            ActivityEntry(
                t,
                ERROR,
                "The DWARF refused the exposure: busy (a GOTO or another session is running)",
            )
        ]

    def _on_abort_superseded(self, f: dict[str, Any], t: float) -> list[ActivityEntry]:
        return [ActivityEntry(t, INFO, "New exposure from NINA starts once the DWARF is ready")]

    def _on_abort_slew_unconfirmed(self, f: dict[str, Any], t: float) -> list[ActivityEntry]:
        return [ActivityEntry(t, WARN, "Slew aborted; the DWARF did not confirm the stop")]

    def _on_calibration_done(self, f: dict[str, Any], t: float) -> list[ActivityEntry]:
        return [ActivityEntry(t, OK, "Calibration completed")]

    def _on_calibration_outcome(self, f: dict[str, Any], t: float) -> list[ActivityEntry]:
        outcome = f.get("outcome")
        if outcome == "failed":
            self.status.telescope = "calibration failed"
            return [ActivityEntry(t, ERROR, f"Calibration failed: {f.get('error')}")]
        if outcome == "not_confirmed":
            return [ActivityEntry(t, WARN, "Calibration not confirmed by the DWARF")]
        return []

    def _on_tracking(self, f: dict[str, Any], t: float) -> list[ActivityEntry]:
        state = str(f.get("state") or "").lower()
        if "track" in state or "running" in state:
            self.status.telescope = "tracking"
        elif "stop" in state or "idle" in state:
            self.status.telescope = "not tracking"
        return []

    def _on_focus_moved(self, f: dict[str, Any], t: float) -> list[ActivityEntry]:
        return [ActivityEntry(t, INFO, f"Focuser at {f.get('position')}", group="focus")]

    def _on_autofocus_start(self, f: dict[str, Any], t: float) -> list[ActivityEntry]:
        return [ActivityEntry(t, WAIT, "Autofocus running…")]

    def _on_autofocus_done(self, f: dict[str, Any], t: float) -> list[ActivityEntry]:
        return [ActivityEntry(t, OK, "Autofocus completed")]

    def _on_autofocus_failed(self, f: dict[str, Any], t: float) -> list[ActivityEntry]:
        return [ActivityEntry(t, ERROR, f"Autofocus failed: {f.get('error')}")]

    def _on_autofocus_not_started(self, f: dict[str, Any], t: float) -> list[ActivityEntry]:
        return [
            ActivityEntry(
                t,
                WARN,
                f"The DWARF did not start autofocus (waited {_num(f.get('waited_seconds'))} s)",
            )
        ]

    def _on_autofocus_skipped(self, f: dict[str, Any], t: float) -> list[ActivityEntry]:
        return [ActivityEntry(t, WARN, "Continuing without autofocus")]

    def _on_startup_calibration_failed(
        self, f: dict[str, Any], t: float
    ) -> list[ActivityEntry]:
        reason = f.get("error") or f.get("error_type") or "unknown error"
        return [ActivityEntry(t, WARN, f"Preparation for the first GOTO failed: {reason}")]

    # endregion

    # region telescope
    def _on_telescope_connected(self, f: dict[str, Any], t: float) -> list[ActivityEntry]:
        self.status.telescope = "connected"
        return [ActivityEntry(t, OK, "Telescope connected by NINA")]

    def _on_telescope_disconnected(self, f: dict[str, Any], t: float) -> list[ActivityEntry]:
        self.status.telescope = "disconnected"
        return [ActivityEntry(t, INFO, "Telescope disconnected by NINA")]

    def _on_tracking_stopped(self, f: dict[str, Any], t: float) -> list[ActivityEntry]:
        self.status.telescope = "not tracking"
        text = "Tracking stopped by NINA: the DWARF no longer follows the target"
        return [ActivityEntry(t, STOP, text)]

    def _on_slew_request(self, f: dict[str, Any], t: float) -> list[ActivityEntry]:
        return [
            ActivityEntry(
                t,
                ACTION,
                f"NINA requested a slew to RA {_num(f.get('ra_hours'), 3)} h, "
                f"Dec {_num(f.get('dec_degrees'), 2)}°",
            )
        ]

    def _on_slew_rejected(self, f: dict[str, Any], t: float) -> list[ActivityEntry]:
        return [
            ActivityEntry(
                t,
                ERROR,
                f"Slew rejected: {f.get('reason')} (reconnect the telescope in NINA)",
            )
        ]

    def _on_slew_failed(self, f: dict[str, Any], t: float) -> list[ActivityEntry]:
        self.status.telescope = "idle"
        return [ActivityEntry(t, ERROR, f"Slew failed: {f.get('detail')}")]

    # endregion

    # region misc
    def _on_battery(self, f: dict[str, Any], t: float) -> list[ActivityEntry]:
        try:
            percent = int(f.get("battery_percent"))
        except (TypeError, ValueError):
            return []
        self.status.battery = percent
        if percent <= LOW_BATTERY_PERCENT and not self._low_battery_warned:
            self._low_battery_warned = True
            return [ActivityEntry(t, WARN, f"DWARF battery low: {percent} %")]
        if percent > LOW_BATTERY_PERCENT + 5:
            self._low_battery_warned = False
        return []

    def _on_http_error(self, f: dict[str, Any], t: float) -> list[ActivityEntry]:
        return [
            ActivityEntry(
                t,
                ERROR,
                "Internal error while handling a NINA request (details in the Technical tab)",
                group="http_error",
            )
        ]

    # endregion
