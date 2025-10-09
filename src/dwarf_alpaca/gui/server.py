from __future__ import annotations

import asyncio
import logging
import threading
from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import Optional

import structlog
import uvicorn
from PySide6.QtCore import QObject, Signal

from ..config.settings import Settings
from ..discovery import DiscoveryService
from ..dwarf.session import configure_session, shutdown_session
from ..server import build_app

logger = logging.getLogger(__name__)


@dataclass
class ServerStatus:
    running: bool
    message: str


class ServerService(QObject):
    """Manages the lifecycle of the Alpaca server inside a background thread."""

    status_changed = Signal(object)
    error_occurred = Signal(str)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._server: Optional[uvicorn.Server] = None
        self._shutdown_event = threading.Event()
        self._running = False

    def is_running(self) -> bool:
        return self._running

    def start(self, settings: Settings) -> None:
        if self._thread and self._thread.is_alive():
            raise RuntimeError("Server is already running")
        self._shutdown_event.clear()
        self._thread = threading.Thread(target=self._thread_main, args=(settings,), daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if not self._loop:
            return

        if self._server is None:
            return

        def _stop_server() -> None:
            if self._server:
                self._server.should_exit = True
                self._server.force_exit = True

        self._loop.call_soon_threadsafe(_stop_server)

    def _thread_main(self, settings: Settings) -> None:
        try:
            asyncio.run(self._run(settings))
        except Exception as exc:  # pragma: no cover - runtime safeguard
            logger.exception("GUI server worker crashed", exc_info=exc)
            self.error_occurred.emit(str(exc))
            self.status_changed.emit(ServerStatus(running=False, message="Crashed"))
        finally:
            self._running = False
            self._loop = None
            self._server = None
            self._thread = None
            self._shutdown_event.set()

    async def _run(self, settings: Settings) -> None:
        structlog.configure(
            processors=[
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.stdlib.add_log_level,
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.stdlib.BoundLogger,
            logger_factory=structlog.stdlib.LoggerFactory(),
        )

        configure_session(settings)
        app = build_app(settings)

        async with AsyncExitStack() as stack:
            discovery: Optional[DiscoveryService] = None
            if settings.discovery_enabled:
                discovery = DiscoveryService(settings)
                await stack.enter_async_context(discovery)

            config = uvicorn.Config(
                app=app,
                host=settings.http_host,
                port=settings.http_port,
                log_level="info",
                access_log=False,
                log_config=None,
            )
            if settings.enable_https and settings.tls_certfile and settings.tls_keyfile:
                config.ssl_certfile = str(settings.tls_certfile)
                config.ssl_keyfile = str(settings.tls_keyfile)

            server = uvicorn.Server(config)
            self._server = server
            self._loop = asyncio.get_running_loop()
            self._running = True
            self.status_changed.emit(ServerStatus(running=True, message="Running"))
            try:
                await server.serve()
            finally:
                await shutdown_session()
                self.status_changed.emit(ServerStatus(running=False, message="Stopped"))
