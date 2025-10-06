from __future__ import annotations

import asyncio
import contextlib
import io
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from ftplib import FTP, all_errors, error_perm
from typing import Iterable

import structlog

logger = structlog.get_logger(__name__)


PHOTO_EXTENSIONS = (".jpg", ".jpeg", ".png", ".fits", ".fit")


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
            if entry and self._is_new_entry(entry, baseline):
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
        roots = ("/Astronomy", "/DWARF_II/Astronomy")
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
            for subdir in subdirs:
                if not subdir.startswith("DWARF_RAW"):
                    continue
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

    def _photo_candidates(self, camera: str) -> Iterable[tuple[str, str]]:
        return (
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
