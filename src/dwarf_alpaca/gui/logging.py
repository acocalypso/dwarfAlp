from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import QObject, Signal


class LogSignalEmitter(QObject):
    """Qt signal bridge for forwarding Python logging records."""

    message = Signal(int, str)


class QtLogHandler(logging.Handler):
    """A logging handler that emits formatted records through Qt signals."""

    def __init__(self, emitter: Optional[LogSignalEmitter] = None) -> None:
        super().__init__()
        self._emitter = emitter or LogSignalEmitter()

    @property
    def emitter(self) -> LogSignalEmitter:
        return self._emitter

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.format(record)
        except Exception:
            message = record.getMessage()
        self._emitter.message.emit(record.levelno, message)
