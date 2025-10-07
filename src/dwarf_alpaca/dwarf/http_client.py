from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Literal, Optional

import httpx
import structlog


logger = structlog.get_logger(__name__)


@dataclass(slots=True)
class DwarfHttpClient:
    """Async HTTP client for DWARF 3 API access.

    The DWARF API exposes a JSON control service on port 8082 and JPEG assets on 8092.
    This client handles retries, timeouts, and automatic base URL switching between
    STA and AP modes.
    """

    host: str
    api_port: int = 8082
    jpeg_port: int = 8092
    timeout: float = 5.0
    retries: int = 3
    scheme: Literal["http", "https"] = "http"
    _client: httpx.AsyncClient | None = None
    _jpeg_client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "DwarfHttpClient":
        await self._ensure_client()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.aclose()

    async def _ensure_client(self) -> None:
        if self._client is None:
            base_url = f"{self.scheme}://{self.host}:{self.api_port}"
            self._client = httpx.AsyncClient(base_url=base_url, timeout=self.timeout)

    async def _ensure_jpeg_client(self) -> None:
        if self._jpeg_client is None:
            base_url = f"{self.scheme}://{self.host}:{self.jpeg_port}"
            self._jpeg_client = httpx.AsyncClient(base_url=base_url, timeout=self.timeout)

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        if self._jpeg_client is not None:
            await self._jpeg_client.aclose()
            self._jpeg_client = None

    async def _request(
        self,
        method: str,
        path: str,
        json: Optional[dict[str, Any]] = None,
        params: Optional[dict[str, Any]] = None,
    ) -> httpx.Response:
        await self._ensure_client()
        assert self._client

        attempt = 0
        last_exc: Exception | None = None
        while attempt < self.retries:
            try:
                response = await self._client.request(method, path, json=json, params=params)
                response.raise_for_status()
                return response
            except (httpx.RequestError, httpx.HTTPStatusError) as exc:
                last_exc = exc
                attempt += 1
                logger.warning(
                    "dwarf.http.retry",
                    method=method,
                    path=path,
                    attempt=attempt,
                    error=str(exc),
                )
                await asyncio.sleep(0.5 * attempt)

        assert last_exc is not None
        raise last_exc

    async def get_json(self, path: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        response = await self._request("GET", path, params=params)
        return response.json()

    async def post_json(
        self,
        path: str,
        payload: dict[str, Any],
        params: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        response = await self._request("POST", path, json=payload, params=params)
        return response.json()

    async def fetch_jpeg(self, path: str) -> bytes:
        await self._ensure_jpeg_client()
        assert self._jpeg_client
        response = await self._jpeg_client.get(path)
        response.raise_for_status()
        return response.content

    def _normalize_media_path(self, file_path: str) -> str:
        if not file_path:
            raise ValueError("file_path must be provided")
        normalized = file_path.strip()
        if normalized.startswith("/sdcard/"):
            normalized = normalized[len("/sdcard/") :]
        normalized = normalized.lstrip("/")
        return f"/{normalized}"

    async def list_album_media_infos(
        self,
        media_type: int = 1,
        *,
        page_index: int = 0,
        page_size: int = 1,
    ) -> list[dict[str, Any]]:
        payload = {
            "mediaType": media_type,
            "pageIndex": page_index,
            "pageSize": page_size,
        }
        try:
            response = await self.post_json("/album/list/mediaInfos", payload)
        except Exception as exc:
            logger.warning(
                "dwarf.http.album_list_failed",
                media_type=media_type,
                page_index=page_index,
                page_size=page_size,
                error=str(exc),
            )
            return []
        data = response.get("data") if isinstance(response, dict) else None
        entries: list[dict[str, Any]] = []
        skipped = 0

        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    entries.append(item)
                else:
                    skipped += 1
        elif isinstance(data, dict):
            for key in ("mediaInfos", "list", "items", "records", "mediaList"):
                value = data.get(key)
                if isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict):
                            entries.append(item)
                        else:
                            skipped += 1
                    break
            else:
                if all(isinstance(v, dict) for v in data.values()):
                    entries.extend(v for v in data.values() if isinstance(v, dict))
                else:
                    logger.debug(
                        "dwarf.http.album_list_dict_unparsed",
                        keys=list(data.keys()),
                    )

        if entries:
            if skipped:
                logger.debug(
                    "dwarf.http.album_list_entries_skipped",
                    skipped=skipped,
                    total=len(entries) + skipped,
                )
            return entries

        logger.warning(
            "dwarf.http.album_list_unexpected",
            payload=payload,
            response_type=type(response).__name__,
            data_type=type(data).__name__ if data is not None else None,
        )
        return []

    async def fetch_media_file(self, file_path: str) -> bytes:
        normalized_path = self._normalize_media_path(file_path)
        await self._ensure_jpeg_client()
        assert self._jpeg_client
        response = await self._jpeg_client.get(normalized_path)
        response.raise_for_status()
        return response.content

    async def get_default_params_config(self) -> dict[str, Any]:
        """Fetch the DWARF parameters configuration payload."""
        response = await self._request("GET", "/getDefaultParamsConfig")
        return response.json()

    async def slew_to_coordinates(self, ra_hours: float, dec_degrees: float) -> dict[str, Any]:
        """Send a go-to command to the DWARF mount."""
        payload = {
            "ra": ra_hours,
            "dec": dec_degrees,
        }
        return await self.post_json("/v1/mount/slewtocoords", payload)

    async def get_mount_status(self) -> dict[str, Any]:
        return await self.get_json("/v1/mount/status")

    async def trigger_exposure(self, duration_s: float, channel: str = "tele") -> dict[str, Any]:
        payload = {
            "duration": duration_s,
            "channel": channel,
        }
        return await self.post_json("/v1/camera/exposure", payload)

    async def get_album_listing(self) -> dict[str, Any]:
        return await self.get_json("/v1/album/list")

    def build_jpeg_url(self, filename: str) -> str:
        normalized = self._normalize_media_path(filename)
        return f"{self.scheme}://{self.host}:{self.jpeg_port}{normalized}"
