from __future__ import annotations

import math
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def _precess_j2000(ra_degrees: float, dec_degrees: float) -> tuple[float, float]:
    """Precess a J2000 catalogue coordinate to the current mean equator/equinox."""

    now = datetime.now(timezone.utc)
    year = now.year + (now.timetuple().tm_yday - 1) / 365.2425
    centuries = (year - 2000.0) / 100.0
    zeta = math.radians(
        (2306.2181 * centuries + 0.30188 * centuries**2 + 0.017998 * centuries**3)
        / 3600.0
    )
    zed = math.radians(
        (2306.2181 * centuries + 1.09468 * centuries**2 + 0.018203 * centuries**3)
        / 3600.0
    )
    theta = math.radians(
        (2004.3109 * centuries - 0.42665 * centuries**2 - 0.041833 * centuries**3)
        / 3600.0
    )
    ra = math.radians(ra_degrees)
    dec = math.radians(dec_degrees)
    a = math.cos(dec) * math.sin(ra + zeta)
    b = (
        math.cos(theta) * math.cos(dec) * math.cos(ra + zeta)
        - math.sin(theta) * math.sin(dec)
    )
    c = (
        math.sin(theta) * math.cos(dec) * math.cos(ra + zeta)
        + math.cos(theta) * math.sin(dec)
    )
    return math.degrees(math.atan2(a, b) + zed) % 360.0, math.degrees(math.asin(c))


def _angular_distance_degrees(
    ra1: float, dec1: float, ra2: float, dec2: float
) -> float:
    ra1_rad, dec1_rad = math.radians(ra1), math.radians(dec1)
    ra2_rad, dec2_rad = math.radians(ra2), math.radians(dec2)
    cosine = (
        math.sin(dec1_rad) * math.sin(dec2_rad)
        + math.cos(dec1_rad) * math.cos(dec2_rad) * math.cos(ra1_rad - ra2_rad)
    )
    return math.degrees(math.acos(max(-1.0, min(1.0, cosine))))


def _default_nina_catalog() -> Path | None:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        return None
    path = Path(local_app_data) / "NINA" / "NINA.sqlite"
    return path if path.is_file() else None


def resolve_nina_target_name(
    ra_hours: float,
    dec_degrees: float,
    *,
    catalog_path: Path | None = None,
    tolerance_degrees: float = 0.08,
) -> str | None:
    """Resolve coordinates against NINA's local sky-atlas catalogue.

    Alpaca's ``SlewToCoordinatesAsync`` method contains no object-name field.
    NINA does, however, install its catalogue beside the application.  Matching
    both J2000 and precessed coordinates lets this work with either NINA epoch
    setting without a network request.
    """

    path = catalog_path or _default_nina_catalog()
    if path is None or not path.is_file():
        return None
    requested_ra = (ra_hours * 15.0) % 360.0
    try:
        connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        try:
            rows = connection.execute("SELECT id, ra, dec FROM dsodetail").fetchall()
            best_id: str | None = None
            best_distance = float("inf")
            for object_id, ra, dec in rows:
                if ra is None or dec is None:
                    continue
                j2000_distance = _angular_distance_degrees(
                    requested_ra, dec_degrees, float(ra), float(dec)
                )
                current_ra, current_dec = _precess_j2000(float(ra), float(dec))
                current_distance = _angular_distance_degrees(
                    requested_ra, dec_degrees, current_ra, current_dec
                )
                distance = min(j2000_distance, current_distance)
                if distance < best_distance:
                    best_id = str(object_id)
                    best_distance = distance
            if best_id is None or best_distance > tolerance_degrees:
                return None
            aliases = connection.execute(
                "SELECT catalogue, designation FROM cataloguenr WHERE dsodetailid = ?",
                (best_id,),
            ).fetchall()
        finally:
            connection.close()
    except (OSError, sqlite3.Error):
        return None

    priorities = {"M": 0, "Caldwell": 1, "NGC": 2, "IC": 3, "NAME": 4}
    aliases.sort(key=lambda item: priorities.get(str(item[0]), 100))
    for catalogue, designation in aliases:
        catalogue, designation = str(catalogue), str(designation).strip()
        if catalogue in priorities and designation:
            if catalogue == "NAME":
                return designation
            return f"{catalogue}{designation}"
    return best_id
