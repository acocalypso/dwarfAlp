from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, Optional

from PySide6.QtCore import QObject, QThread, Signal


CoroutineFactory = Callable[[], Awaitable[Any]]


class AsyncWorker(QThread):
    """QThread wrapper that executes an asyncio coroutine factory."""

    finished_success = Signal(object)
    finished_error = Signal(Exception)
    status = Signal(str)

    def __init__(self, coro_factory: CoroutineFactory, *, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._coro_factory = coro_factory

    def run(self) -> None:  # type: ignore[override]
        try:
            result = asyncio.run(self._execute())
        except Exception as exc:  # pragma: no cover - GUI thread execution
            self.finished_error.emit(exc)
        else:
            self.finished_success.emit(result)

    async def _execute(self) -> Any:
        self.status.emit("running")
        result = await self._coro_factory()
        self.status.emit("finished")
        return result
