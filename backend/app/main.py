import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError, OperationalError

from app.core.config import settings
from app.core.logging import log_requests, setup_logging
from app.db.session import engine
from app.deps import DbSession, client_ip
from app.models import LogLevel, MetricName
from app.realtime.buffer import metric_buffer
from app.realtime.manager import manager
from app.realtime.simulator import MetricSimulator, run_simulator
from app.routers import admin, analytics, auth, metrics, records, users, ws
from app.services import audit_service

setup_logging(settings.log_level)
logger = logging.getLogger(__name__)


def start_realtime_tasks() -> list[asyncio.Task]:
    """Start the simulator and the batch writer in this process."""
    simulator = MetricSimulator(
        settings.simulator_servers,
        {
            MetricName.cpu: settings.threshold_cpu,
            MetricName.memory: settings.threshold_memory,
            MetricName.temperature: settings.threshold_temperature,
        },
    )
    logger.info(
        "Simulator started for %s; batch writes every %ss or %d metrics",
        ", ".join(settings.simulator_servers),
        settings.batch_interval_seconds,
        settings.batch_size,
    )
    return [
        asyncio.create_task(run_simulator(simulator, manager, metric_buffer)),
        asyncio.create_task(metric_buffer.run()),
    ]


@asynccontextmanager
async def lifespan(app: FastAPI):
    tasks = start_realtime_tasks() if settings.simulator_enabled else []
    yield
    # Stop both tasks first, then write what is left ourselves, so two
    # writes never run at the same time
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    if tasks:
        await metric_buffer.flush("shutdown")
    await engine.dispose()


app = FastAPI(
    title="Analytics Monitoring System API",
    version="0.1.0",
    lifespan=lifespan,
)


async def handle_unexpected_errors(request: Request, call_next):
    """Turn any unhandled exception into a plain 500.

    The traceback goes to stdout and a server_error audit event is written;
    the client never sees internal details.
    """
    try:
        return await call_next(request)
    except Exception as exc:
        logger.exception(
            "Unhandled error on %s %s", request.method, request.url.path
        )
        await audit_service.log(
            "server_error",
            f"{request.method} {request.url.path} raised "
            f"{type(exc).__name__}: {exc}",
            level=LogLevel.ERROR,
            ip_address=client_ip(request),
        )
        return JSONResponse(
            status_code=500, content={"detail": "Internal server error"}
        )


# The middleware added last runs first: log_requests wraps the error handler,
# so a request that ends in a 500 still gets its request log line.
app.middleware("http")(handle_unexpected_errors)
app.middleware("http")(log_requests)


@app.exception_handler(OperationalError)
async def database_unavailable(
    request: Request, exc: OperationalError
) -> JSONResponse:
    """Lost or refused database connection: 503 instead of a 500.

    Every protected endpoint reads the user from the database, so this
    covers them all.
    """
    logger.warning("Database unavailable: %s", exc.orig)
    return JSONResponse(
        status_code=503, content={"detail": "Database unavailable"}
    )


app.include_router(auth.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")
app.include_router(records.router, prefix="/api/v1")
app.include_router(metrics.router, prefix="/api/v1")
app.include_router(analytics.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")
app.include_router(ws.router)


@app.get("/health", tags=["health"])
async def health(db: DbSession) -> dict[str, str]:
    """Used by the Compose healthcheck; also checks the database."""
    try:
        await db.execute(select(1))
    except DBAPIError as exc:
        raise HTTPException(
            status_code=503, detail="Database unavailable"
        ) from exc
    return {"status": "ok"}
