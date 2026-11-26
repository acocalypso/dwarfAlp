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


class ActivitySignalEmitter(QObject):
    """Qt signal bridge carrying the raw message and its creation time."""

    record = Signal(str, float)


class ActivityLogHandler(logging.Handler):
    """Forward raw log messages to the plain-language activity feed.

    Unlike :class:`QtLogHandler` it does not format the record: the activity
    translator needs the original structlog JSON (or ``name key=value``) text.
    """

    def __init__(self, emitter: Optional[ActivitySignalEmitter] = None) -> None:
        super().__init__(level=logging.INFO)
        self._emitter = emitter or ActivitySignalEmitter()

    @property
    def emitter(self) -> ActivitySignalEmitter:
        return self._emitter

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = record.getMessage()
        except Exception:
            return
        self._emitter.record.emit(message, float(record.created))
