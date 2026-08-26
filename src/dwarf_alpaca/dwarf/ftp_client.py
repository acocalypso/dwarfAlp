from __future__ import annotations

import asyncio
import contextlib
import io
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from ftplib import FTP, all_errors, error_perm
from typing import Iterable

import structlog

logger = structlog.get_logger(__name__)


PHOTO_EXTENSIONS = (".jpg", ".jpeg", ".png", ".fits", ".fit")
CAPTURE_CLOCK_TOLERANCE_SECONDS = 10.0


@dataclass(slots=True)
class FtpPhotoEntry:
    """Metadata describing a single DWARF FTP photo asset."""

    directory: str
    name: str
    timestamp: float
    path: str


@dataclass(slots=True)
class FtpPhotoCapture:
    """A fetched DWARF FTP photo asset and its metadata."""

    entry: FtpPhotoEntry
    content: bytes


@dataclass(slots=True)
class DwarfFtpClient:
    """Lightweight async wrapper around DWARF's anonymous FTP service."""

    host: str
    port: int = 21
    timeout: float = 10.0
    passive: bool = True
    username: str = "Anonymous"
    password: str = ""
    poll_interval: float = 1.0
    max_astro_directories_per_scan: int = 8

    async def get_latest_photo_entry(
        self,
        camera: str = "TELE",
        *,
        capture_kind: str = "photo",
    ) -> FtpPhotoEntry | None:
        """Return the most recent capture entry for the given camera, if any."""

        return await asyncio.to_thread(
            self._get_latest_photo_entry_sync,
            camera.upper(),
            capture_kind,
        )

    async def wait_for_new_photo(
        self,
        baseline: FtpPhotoEntry | None,
        *,
        camera: str = "TELE",
        timeout: float = 30.0,
        capture_kind: str = "photo",
        not_before: float | None = None,
    ) -> FtpPhotoCapture | None:
        """Poll the FTP service until a new photo appears relative to the baseline."""

        deadline = time.time() + max(timeout, 0.1)
        camera_upper = camera.upper()
        attempt = 0
        while time.time() < deadline:
            attempt += 1
            try:
                entry = await self.get_latest_photo_entry(
                    camera_upper,
                    capture_kind=capture_kind,
                )
            except all_errors as exc:
                logger.warning(
                    "dwarf.ftp.latest_failed",
                    camera=camera_upper,
                    error=str(exc),
                    attempt=attempt,
                )
                entry = None
            if entry and self._is_new_entry(entry, baseline) and self._is_current_capture(
                entry,
                not_before,
            ):
                try:
                    content = await asyncio.to_thread(self._download_file_sync, entry.path)
                except all_errors as exc:
                    logger.warning(
                        "dwarf.ftp.download_failed",
                        camera=camera_upper,
                        path=entry.path,
                        error=str(exc),
                    )
                else:
                    return FtpPhotoCapture(entry=entry, content=content)
            await asyncio.sleep(self.poll_interval)
        return None

    def _get_latest_photo_entry_sync(
        self,
        camera: str,
        capture_kind: str,
    ) -> FtpPhotoEntry | None:
        def operation(ftp: FTP) -> FtpPhotoEntry | None:
            if capture_kind == "astro":
                entries = self._collect_astro_entries(ftp)
            else:
                entries = self._collect_photo_entries(ftp, camera)
            if not entries:
                return None
            entries.sort(key=lambda item: (item.timestamp, item.path))
            return entries[-1]

        return self._with_connection(operation)

    def _with_connection(self, operation):
        ftp = FTP()
        ftp.connect(self.host, self.port, timeout=self.timeout)
        ftp.login(self.username, self.password)
        ftp.set_pasv(self.passive)
        try:
            return operation(ftp)
        finally:
            with contextlib.suppress(Exception):
                ftp.quit()

    def _collect_photo_entries(self, ftp: FTP, camera: str) -> list[FtpPhotoEntry]:
        camera_upper = camera.upper()
        entries: list[FtpPhotoEntry] = []
        for directory, prefix in self._photo_candidates(camera_upper):
            try:
                previous = ftp.pwd()
            except error_perm:
                previous = "/"
            try:
                ftp.cwd(directory)
            except error_perm:
                continue
            try:
                filenames = ftp.nlst()
            except error_perm:
                filenames = []
            for name in filenames:
                if not name.startswith(prefix):
                    continue
                if not self._matches_extension(name):
                    continue
                timestamp = self._fetch_timestamp(ftp, name)
                path = f"{directory.rstrip('/')}/{name}"
                entries.append(
                    FtpPhotoEntry(directory=directory, name=name, timestamp=timestamp, path=path)
                )
            try:
                ftp.cwd(previous)
            except error_perm:
                ftp.cwd("/")
        return entries

    def _collect_astro_entries(self, ftp: FTP) -> list[FtpPhotoEntry]:
        roots = ("/Astronomy", "/DWARF_mini/Astronomy", "/DWARF_II/Astronomy")
        entries: list[FtpPhotoEntry] = []
        try:
            start_dir = ftp.pwd()
        except error_perm:
            start_dir = "/"
        for root in roots:
            try:
                ftp.cwd(root)
            except error_perm:
                continue
            try:
                subdirs = ftp.nlst()
            except error_perm:
                subdirs = []
            capture_dirs = [
                subdir for subdir in subdirs if subdir.startswith("DWARF_RAW")
            ]
            # A Mini with a populated SD card can have hundreds of astronomy
            # directories. Walking all of them took 26 seconds on hardware and
            # caused the poller to finish before a new FITS appeared. Capture
            # directory names end in a firmware timestamp, so inspect only the
            # newest handful on each poll.
            capture_dirs.sort(key=self._astro_directory_sort_key, reverse=True)
            for subdir in capture_dirs[: max(1, self.max_astro_directories_per_scan)]:
                full_dir = f"{root.rstrip('/')}/{subdir}"
                try:
                    ftp.cwd(full_dir)
                except error_perm:
                    continue
                try:
                    filenames = ftp.nlst()
                except error_perm:
                    filenames = []
                for name in filenames:
                    lower = name.lower()
                    if not lower.endswith((".fits", ".fit")):
                        continue
                    # Stacked FITS files are cumulative firmware products, not
                    # the single raw exposure requested by an ASCOM client.
                    # Returning one can also select an older completed stack
                    # while the requested raw frame is still being written.
                    if lower.startswith("stacked"):
                        continue
                    timestamp = self._fetch_timestamp(ftp, name)
                    path = f"{full_dir.rstrip('/')}/{name}"
                    entries.append(
                        FtpPhotoEntry(directory=full_dir, name=name, timestamp=timestamp, path=path)
                    )
                try:
                    ftp.cwd(root)
                except error_perm:
                    ftp.cwd("/")
            try:
                ftp.cwd(start_dir)
            except error_perm:
                ftp.cwd("/")
        return entries

    @staticmethod
    def _astro_directory_sort_key(directory: str) -> int:
        name = directory.rsplit("/", 1)[-1]
        matches = re.findall(
            r"20\d{2}(?:[-_]?\d{2}){5}(?:[-_]?\d{3})?",
            name,
        )
        if not matches:
            return 0
        digits = re.sub(r"\D", "", matches[-1])
        return int(digits.ljust(17, "0")[:17])

    def _photo_candidates(self, camera: str) -> Iterable[tuple[str, str]]:
        return (
            ("/DWARF_mini/Normal_Photos", f"DWARF_mini_{camera}"),
            ("/Normal_Photos", f"DWARF3_{camera}"),
            ("/DWARF_II/Normal_Photos", f"DWARF_{camera}"),
        )

    def _matches_extension(self, name: str) -> bool:
        lower = name.lower()
        return lower.endswith(PHOTO_EXTENSIONS)

    def _fetch_timestamp(self, ftp: FTP, name: str) -> float:
        try:
            response = ftp.sendcmd(f"MDTM {name}")
        except error_perm:
            return time.time()
        return self._parse_mdtm(response)

    @staticmethod
    def _parse_mdtm(response: str) -> float:
        value = response.strip()
        if " " in value:
            value = value.split()[1]
        try:
            dt = datetime.strptime(value, "%Y%m%d%H%M%S")
        except ValueError:
            return time.time()
        return dt.replace(tzinfo=timezone.utc).timestamp()

    def _download_file_sync(self, path: str) -> bytes:
        def operation(ftp: FTP) -> bytes:
            buffer = io.BytesIO()
            ftp.retrbinary(f"RETR {path}", buffer.write)
            return buffer.getvalue()

        return self._with_connection(operation)

    @staticmethod
    def _is_new_entry(entry: FtpPhotoEntry, baseline: FtpPhotoEntry | None) -> bool:
        if baseline is None:
            return True
        if entry.timestamp > baseline.timestamp + 1e-6:
            return True
        return entry.path != baseline.path

    @classmethod
    def _is_current_capture(
        cls,
        entry: FtpPhotoEntry,
        not_before: float | None,
    ) -> bool:
        if not_before is None:
            return True

        # MDTM is not trustworthy on all firmware versions: some servers
        # report the time of the directory scan rather than the file. DWARF
        # astronomy paths contain the actual local capture timestamp, so use
        # that whenever it is available.
        embedded = cls._embedded_capture_timestamp(entry.path)
        observed = embedded if embedded is not None else entry.timestamp
        is_current = observed >= not_before - CAPTURE_CLOCK_TOLERANCE_SECONDS
        if not is_current:
            logger.debug(
                "dwarf.ftp.stale_entry_ignored",
                path=entry.path,
                embedded_timestamp=embedded,
                mdtm_timestamp=entry.timestamp,
                not_before=not_before,
            )
        return is_current

    @staticmethod
    def _embedded_capture_timestamp(path: str) -> float | None:
        matches: list[datetime] = []
        for match in re.finditer(
            r"(?<!\d)(20\d{2})[-_](\d{2})[-_](\d{2})[-_](\d{2})[-_](\d{2})[-_](\d{2})(?:[-_](\d{3}))?(?!\d)",
            path,
        ):
            year, month, day, hour, minute, second = (
                int(value) for value in match.groups()[:6]
            )
            milliseconds = int(match.group(7) or 0)
            with contextlib.suppress(ValueError):
                matches.append(
                    datetime(year, month, day, hour, minute, second, milliseconds * 1000)
                )
        for match in re.finditer(
            r"(?<!\d)(20\d{6})[-_](\d{6})(\d{3})?(?!\d)",
            path,
        ):
            value = "".join(match.groups()[:2])
            with contextlib.suppress(ValueError):
                parsed = datetime.strptime(value, "%Y%m%d%H%M%S")
                matches.append(parsed.replace(microsecond=int(match.group(3) or 0) * 1000))
        if not matches:
            return None
        # A filename timestamp is normally later than its directory start
        # timestamp and therefore best represents when the frame was written.
        return max(matches).timestamp()
