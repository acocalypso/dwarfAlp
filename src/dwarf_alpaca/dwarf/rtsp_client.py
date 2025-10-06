from __future__ import annotations

import asyncio
from collections import deque
from typing import Deque, Optional

import av
import numpy as np
import structlog


logger = structlog.get_logger(__name__)


class DwarfRtspClient:
    """RTSP frame reader for DWARF live view streams."""

    def __init__(
        self,
        url: str,
        *,
        buffer_size: int = 10,
        preferred_format: str = "bgr24",
    ) -> None:
        self.url = url
        self.buffer_size = buffer_size
        self.preferred_format = preferred_format

        self._queue: asyncio.Queue[np.ndarray] | None = None
        self._task: asyncio.Task[None] | None = None
        self._stop_event: asyncio.Event | None = None

    async def start(self) -> None:
        if self._task and not self._task.done():
            return

        self._queue = asyncio.Queue(maxsize=self.buffer_size)
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(self._reader())
        logger.info("rtsp.started", url=self.url)

    async def stop(self) -> None:
        if self._stop_event:
            self._stop_event.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        self._queue = None
        logger.info("rtsp.stopped", url=self.url)

    async def read_frame(self) -> np.ndarray:
        if self._queue is None:
            raise RuntimeError("RTSP client not started")
        return await self._queue.get()

    async def _reader(self) -> None:
        assert self._stop_event is not None
        queue = self._queue
        assert queue is not None

        try:
            container = await asyncio.to_thread(av.open, self.url, format="rtsp")
        except Exception as exc:  # pragma: no cover - dependent on environment
            logger.error("rtsp.open_failed", url=self.url, error=str(exc))
            return

        try:
            stream = container.streams.video[0]
            stream.thread_type = "AUTO"
            for frame in container.decode(stream):
                if self._stop_event.is_set():
                    break
                img = frame.to_ndarray(format=self.preferred_format)
                while True:
                    try:
                        queue.put_nowait(img)
                        break
                    except asyncio.QueueFull:
                        try:
                            queue.get_nowait()
                        except asyncio.QueueEmpty:
                            break
                await asyncio.sleep(0)
        finally:
            container.close()
