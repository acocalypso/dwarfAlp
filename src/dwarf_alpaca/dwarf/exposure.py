from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator, Sequence

import math
import re

_DURATION_KEYS: Sequence[str] = (
    "duration",
    "time",
    "exp_time",
    "exptime",
    "value",
    "text",
    "name",
)

_FRACTION_RE = re.compile(r"^\s*(\d+)\s*/\s*(\d+)")
_FLOAT_RE = re.compile(r"^\s*([0-9]*\.?[0-9]+)")


@dataclass(frozen=True)
class ExposureOption:
    index: int
    seconds: float


@dataclass
class ExposureResolver:
    """Maps desired exposure durations to DWARF exposure indices."""

    options: list[ExposureOption]

    @classmethod
    def from_config(cls, config: Any) -> ExposureResolver | None:
        options = cls._extract_camera_options(config)
        if not options:
            options = list(cls._discover_options(config))
        if not options:
            return None
        # de-duplicate by index keeping the smallest duration delta entry
        dedup: dict[int, ExposureOption] = {}
        for option in options:
            if option.index in dedup:
                existing = dedup[option.index]
                if option.seconds < existing.seconds:
                    dedup[option.index] = option
            else:
                dedup[option.index] = option
        ordered = sorted(dedup.values(), key=lambda entry: entry.seconds)
        if not ordered:
            return None
        return cls(ordered)

    @classmethod
    def _extract_camera_options(cls, config: Any) -> list[ExposureOption]:
        data = config
        if isinstance(data, dict) and "data" in data:
            data = data["data"]
        cameras: Any = None
        if isinstance(data, dict):
            cameras = data.get("cameras")
        if not isinstance(cameras, list):
            return []

        preferred: list[ExposureOption] | None = None
        fallback: list[ExposureOption] | None = None

        for camera in cameras:
            options = cls._extract_camera_exposures(camera)
            if not options:
                continue
            camera_id = camera.get("id") if isinstance(camera, dict) else None
            camera_name = (
                str(camera.get("name", "")).strip().lower() if isinstance(camera, dict) else ""
            )
            if camera_id == 0 or camera_name == "tele":
                preferred = options
                break
            if fallback is None:
                fallback = options

        return preferred or fallback or []

    @staticmethod
    def _extract_camera_exposures(camera: Any) -> list[ExposureOption]:
        if not isinstance(camera, dict):
            return []
        params = camera.get("supportParams")
        if not isinstance(params, list):
            return []
        for param in params:
            if not isinstance(param, dict):
                continue
            name = str(param.get("name", "")).strip().lower()
            if name != "exposure":
                continue
            gear_mode = param.get("gearMode")
            if not isinstance(gear_mode, dict):
                return []
            values = gear_mode.get("values")
            if not isinstance(values, list):
                return []
            options: list[ExposureOption] = []
            for entry in values:
                if not isinstance(entry, dict) or "index" not in entry:
                    continue
                try:
                    index = int(entry["index"])
                except (TypeError, ValueError):
                    continue
                duration = ExposureResolver._parse_duration(entry.get("name"))
                if duration is None or duration <= 0:
                    continue
                options.append(ExposureOption(index=index, seconds=duration))
            return options
        return []

    @classmethod
    def _discover_options(cls, node: Any) -> Iterator[ExposureOption]:
        if isinstance(node, dict):
            lowered = {key.lower(): key for key in node.keys()}
            if "index" in lowered:
                index_value = node[lowered["index"]]
                try:
                    index_int = int(index_value)
                except (TypeError, ValueError):
                    index_int = None
                duration = cls._extract_duration(node, lowered)
                if index_int is not None and duration is not None and duration > 0:
                    yield ExposureOption(index=index_int, seconds=duration)
            for value in node.values():
                yield from cls._discover_options(value)
        elif isinstance(node, list):
            for item in node:
                yield from cls._discover_options(item)

    @staticmethod
    def _extract_duration(node: dict[str, Any], lowered: dict[str, str]) -> float | None:
        for key in _DURATION_KEYS:
            if key in lowered:
                raw_value = node[lowered[key]]
                parsed = ExposureResolver._parse_duration(raw_value)
                if parsed is not None:
                    return parsed
        return None

    @staticmethod
    def _parse_duration(value: Any) -> float | None:
        if isinstance(value, (int, float)):
            seconds = float(value)
            if seconds <= 0 or math.isnan(seconds):
                return None
            return seconds
        if isinstance(value, str):
            candidate = value.strip().lower()
            if not candidate:
                return None
            multiplier = 1.0
            if candidate.endswith("ms"):
                multiplier = 0.001
                candidate = candidate[:-2]
            elif candidate.endswith("s"):
                candidate = candidate[:-1]
            candidate = (
                candidate.replace("seconds", "")
                .replace("second", "")
                .replace("sec", "")
                .replace("\u2033", "")  # double prime symbol
                .replace("\"", "")
                .strip()
            )
            if any(char.isalpha() for char in candidate):
                return None
            if not candidate:
                return None
            fraction_match = _FRACTION_RE.match(candidate)
            if fraction_match:
                numerator = int(fraction_match.group(1))
                denominator = int(fraction_match.group(2))
                if denominator == 0:
                    return None
                return (numerator / denominator) * multiplier
            float_match = _FLOAT_RE.match(candidate)
            if float_match:
                seconds = float(float_match.group(1)) * multiplier
                if seconds <= 0 or math.isnan(seconds):
                    return None
                return seconds
        return None

    def choose_index(self, duration: float) -> int | None:
        if not self.options or duration <= 0:
            return None
        target = float(duration)
        best_option = min(self.options, key=lambda opt: abs(opt.seconds - target))
        return best_option.index

    def available_durations(self) -> list[float]:
        return [option.seconds for option in self.options]

    def __bool__(self) -> bool:
        return bool(self.options)


def flatten_exposure_entries(config: Any) -> list[tuple[int, float]]:
    camera_options = ExposureResolver._extract_camera_options(config)
    if camera_options:
        return [(option.index, option.seconds) for option in camera_options]
    return [(option.index, option.seconds) for option in ExposureResolver._discover_options(config)]
