from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import settings
from app.core.logging import log_requests, setup_logging

setup_logging(settings.log_level)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Background tasks (simulator, batch writer) start here in later tasks.
    yield


app = FastAPI(
    title="Analytics Monitoring System API",
    version="0.1.0",
    lifespan=lifespan,
)
app.middleware("http")(log_requests)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    """Liveness check used by the Docker Compose healthcheck."""
    return {"status": "ok"}
