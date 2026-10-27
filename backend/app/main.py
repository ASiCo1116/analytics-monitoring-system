from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import log_requests, setup_logging
from app.db.session import engine, get_db

setup_logging(settings.log_level)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Background tasks (simulator, batch writer) start here in later tasks.
    yield
    await engine.dispose()


app = FastAPI(
    title="Analytics Monitoring System API",
    version="0.1.0",
    lifespan=lifespan,
)
app.middleware("http")(log_requests)


@app.get("/health", tags=["health"])
async def health(db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    """Health check used by the Docker Compose healthcheck; also verifies the database connection."""
    try:
        await db.execute(select(1))
    except DBAPIError as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc
    return {"status": "ok"}
