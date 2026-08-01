from __future__ import annotations

import asyncio
import logging
import time
from contextlib import AsyncExitStack, asynccontextmanager, suppress

import structlog
import uvicorn
from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from .config.settings import Settings, normalize_dwarf_device_model
from .device_profile import configure_device_profile, get_device_profile
from .devices.camera import router as camera_router
from .devices.filterwheel import preload_filters
from .devices.filterwheel import router as filterwheel_router
from .devices.focuser import router as focuser_router
from .devices.telescope import configure_site_location
from .devices.telescope import router as telescope_router
from .discovery import DiscoveryService
from .dwarf.session import configure_session, get_session, shutdown_session
from .management.router import router as management_router

logger = structlog.get_logger(__name__)


async def _calibrate_after_start(settings: Settings) -> None:
    model = normalize_dwarf_device_model(settings.dwarf_device_model)
    if settings.force_simulation or not settings.calibrate_after_server_start:
        return
    session = None
    acquired = False
    try:
        session = await get_session()
        await session.acquire("telescope")
        acquired = True
        logger.info("server.calibration_after_start.begin", model=model)
        await session.ensure_calibration()
        logger.info("server.calibration_after_start.completed", model=model)
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # pragma: no cover - hardware dependent
        logger.warning(
            "server.calibration_after_start.failed",
            model=model,
            error=str(exc),
            error_type=type(exc).__name__,
        )
    finally:
        if session is not None and acquired:
            await session.release("telescope")


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
    configure_device_profile(settings)
    configure_site_location(settings.site_latitude, settings.site_longitude)
    profile = get_device_profile(settings.dwarf_device_model)

    @asynccontextmanager
    async def _lifespan(app: FastAPI):
        await preload_filters()
        calibration_task: asyncio.Task[None] | None = None
        if settings.calibrate_after_server_start:
            calibration_task = asyncio.create_task(_calibrate_after_start(settings))
        try:
            yield
        finally:
            if calibration_task and not calibration_task.done():
                calibration_task.cancel()
                with suppress(asyncio.CancelledError):
                    await calibration_task
            await shutdown_session()

    app = FastAPI(
        title=f"{profile.display_name} Alpaca Server",
        version="0.1.0",
        lifespan=_lifespan,
    )
    configure_session(settings)
    app.include_router(management_router, prefix="/management")
    app.include_router(telescope_router, prefix="/api/v1/telescope/0")
    app.include_router(camera_router, prefix="/api/v1/camera/0")
    app.include_router(focuser_router, prefix="/api/v1/focuser/0")
    app.include_router(filterwheel_router, prefix="/api/v1/filterwheel/0")
    app.add_middleware(AccessLogMiddleware)

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
