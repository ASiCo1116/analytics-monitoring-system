import asyncio

from sqlalchemy import func, select

from app.core.config import settings
from app.main import app, lifespan
from app.models import Metric
from app.realtime.buffer import metric_buffer


async def test_simulator_runs_and_rest_is_written_on_shutdown(monkeypatch, db):
    monkeypatch.setattr(settings, "simulator_enabled", True)

    async with lifespan(app):
        # Ticks at 0 s and 1 s; the 10-second batch interval is not reached
        await asyncio.sleep(1.5)
        assert len(metric_buffer) == 18

    count = await db.scalar(select(func.count()).select_from(Metric))
    assert count == 18
    assert len(metric_buffer) == 0
    assert metric_buffer.last_flush.reason == "shutdown"
