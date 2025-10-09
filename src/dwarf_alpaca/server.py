from __future__ import annotations

import asyncio
import logging
import time
from contextlib import AsyncExitStack, asynccontextmanager

import structlog
import uvicorn
from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from .config.settings import Settings
from .discovery import DiscoveryService
from .management.router import router as management_router
from .devices.telescope import router as telescope_router
from .devices.camera import router as camera_router
from .devices.filterwheel import preload_filters, router as filterwheel_router
from .devices.focuser import router as focuser_router
from .dwarf.session import configure_session, shutdown_session

logger = structlog.get_logger(__name__)


class AccessLogMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: FastAPI) -> None:
        super().__init__(app)
        self._logger = logging.getLogger("http.access")

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - start) * 1000.0
            self._logger.error(
                "http.request.error",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "query": request.url.query or None,
                    "duration_ms": duration_ms,
                },
                exc_info=True,
            )
            raise

        status = response.status_code
        if status != 200:
            duration_ms = (time.perf_counter() - start) * 1000.0
            extra = {
                "method": request.method,
                "path": request.url.path,
                "query": request.url.query or None,
                "status_code": status,
                "duration_ms": duration_ms,
            }
            if status >= 500:
                self._logger.error("http.request", extra=extra)
            elif status >= 400:
                self._logger.warning("http.request", extra=extra)
            else:
                self._logger.info("http.request", extra=extra)
        return response


def build_app(settings: Settings) -> FastAPI:
    """Create the FastAPI application with Alpaca management endpoints mounted."""
    app = FastAPI(title="DWARF 3 Alpaca Server", version="0.1.0")
    configure_session(settings)
    app.include_router(management_router, prefix="/management")
    app.include_router(telescope_router, prefix="/api/v1/telescope/0")
    app.include_router(camera_router, prefix="/api/v1/camera/0")
    app.include_router(focuser_router, prefix="/api/v1/focuser/0")
    app.include_router(filterwheel_router, prefix="/api/v1/filterwheel/0")
    app.add_middleware(AccessLogMiddleware)

    @asynccontextmanager
    async def _lifespan(app: FastAPI):
        await preload_filters()
        try:
            yield
        finally:
            await shutdown_session()

    app.router.lifespan_context = _lifespan

    return app


async def run_server(settings: Settings) -> None:
    """Launch the Alpaca server and discovery responder."""
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

    app = build_app(settings)

    async with AsyncExitStack() as stack:
        if settings.discovery_enabled:
            discovery = DiscoveryService(settings)
            await stack.enter_async_context(discovery)

        config = uvicorn.Config(
            app=app,
            host=settings.http_host,
            port=settings.http_port,
            log_level="info",
            access_log=False,
        )
        if settings.enable_https and settings.tls_certfile and settings.tls_keyfile:
            config.ssl_certfile = str(settings.tls_certfile)
            config.ssl_keyfile = str(settings.tls_keyfile)

        server = uvicorn.Server(config)
        logger.info(
            "server.starting",
            host=settings.http_host,
            port=settings.http_port,
            scheme="https" if settings.enable_https else "http",
        )
        await server.serve()

    logger.info("server.stopped")
