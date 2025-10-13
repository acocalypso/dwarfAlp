from __future__ import annotations

import asyncio
import logging
import threading
from contextlib import AsyncExitStack, suppress
from dataclasses import dataclass
from typing import Optional

import structlog
import uvicorn
from PySide6.QtCore import QObject, Signal

from ..config.settings import Settings
from ..discovery import DiscoveryService
from ..dwarf.session import configure_session, get_session, shutdown_session
from ..server import build_app

logger = logging.getLogger(__name__)


@dataclass
class ServerStatus:
    running: bool
    message: str
    has_master_lock: Optional[bool] = None


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
            server = self._server
            if not server:
                return

            async def _shutdown() -> None:
                server.should_exit = True
                with suppress(Exception):
                    await server.shutdown()

            asyncio.create_task(_shutdown())

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
            monitor_task = asyncio.create_task(self._master_lock_monitor())
            try:
                await server.serve()
            finally:
                monitor_task.cancel()
                with suppress(asyncio.CancelledError):
                    await monitor_task
                await shutdown_session()
                self._running = False
                self.status_changed.emit(ServerStatus(running=False, message="Stopped"))

    async def _master_lock_monitor(self) -> None:
        last_value: Optional[bool] = None
        try:
            while True:
                has_lock: Optional[bool] = None
                session = None
                try:
                    session = await get_session()
                except Exception:  # pragma: no cover - defensive monitor
                    logger.debug("GUI master lock monitor error", exc_info=True)
                else:
                    ws_client = getattr(session, "_ws_client", None)
                    ws_connected = bool(getattr(ws_client, "connected", False)) if ws_client else False

                    if not ws_connected:
                        try:
                            ensure_ws = getattr(session, "_ensure_ws", None)
                            if ensure_ws:
                                await ensure_ws()
                                ws_connected = bool(getattr(ws_client, "connected", False)) if ws_client else False
                        except Exception:  # pragma: no cover - defensive monitor
                            logger.debug("GUI master lock reconnect failed", exc_info=True)
                            ws_connected = False

                    if ws_connected:
                        try:
                            ensure_lock = getattr(session, "_ensure_master_lock", None)
                            if ensure_lock:
                                await ensure_lock()
                            has_lock = bool(getattr(session, "has_master_lock", False))
                        except Exception:  # pragma: no cover - defensive monitor
                            logger.debug("GUI master lock read failed", exc_info=True)
                            has_lock = None
                    else:
                        has_lock = None

                if has_lock != last_value:
                    last_value = has_lock
                    self.status_changed.emit(
                        ServerStatus(
                            running=self._running,
                            message="Running" if self._running else "Stopped",
                            has_master_lock=has_lock,
                        )
                    )

                await asyncio.sleep(2.0)
        except asyncio.CancelledError:
            raise
