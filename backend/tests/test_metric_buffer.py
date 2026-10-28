"""MetricBuffer triggers and failure handling, with short intervals."""

import asyncio
import logging
import time
from contextlib import asynccontextmanager

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from app.db.base import utc_now
from app.db.session import SessionLocal
from app.models import Metric, MetricName, SystemLog
from app.realtime.buffer import MetricBuffer
from app.schemas.metric import MetricSample


def make_samples(count: int, start: int = 0) -> list[MetricSample]:
    now = utc_now().replace(microsecond=0)
    return [
        MetricSample(
            server="server-1",
            metric=MetricName.cpu,
            value=i,
            unit="%",
            threshold=90,
            is_anomaly=False,
            recorded_at=now,
        )
        for i in range(start, start + count)
    ]


async def count_rows(model) -> int:
    # A new session each time: an open transaction would keep seeing an
    # old snapshot (REPEATABLE READ)
    async with SessionLocal() as session:
        return await session.scalar(select(func.count()).select_from(model))


async def wait_until(condition, timeout: float = 3) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError("condition not met in time")
        await asyncio.sleep(0.01)


@asynccontextmanager
async def broken_session():
    raise OperationalError("INSERT", {}, Exception("Can't connect to server"))
    yield


class FlakyDatabase:
    """Session factory that fails until `fail` is set to False."""

    def __init__(self) -> None:
        self.fail = True
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return broken_session() if self.fail else SessionLocal()


@pytest.fixture
async def start():
    """Start buffer.run() as a task; cancelled after the test."""
    tasks = []

    def _start(buffer: MetricBuffer) -> None:
        tasks.append(asyncio.create_task(buffer.run()))

    yield _start
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


async def test_interval_trigger(start):
    buffer = MetricBuffer(batch_size=100, interval=0.3)
    buffer.add(make_samples(30))
    start(buffer)

    await asyncio.sleep(0.1)
    assert buffer.last_flush is None  # not before the interval

    await wait_until(lambda: buffer.last_flush is not None)
    assert await count_rows(Metric) == 30
    assert len(buffer) == 0
    assert buffer.last_flush.count == 30
    assert buffer.last_flush.reason == "interval"


async def test_size_trigger(start):
    buffer = MetricBuffer(batch_size=10, interval=30)
    start(buffer)

    buffer.add(make_samples(10))

    # Long before the 30-second interval
    await wait_until(lambda: buffer.last_flush is not None, timeout=1)
    assert buffer.last_flush.reason == "size"
    assert buffer.last_flush.count == 10
    assert await count_rows(Metric) == 10


async def test_empty_buffer_writes_nothing(start):
    database = FlakyDatabase()
    buffer = MetricBuffer(
        batch_size=10, interval=0.05, session_factory=database
    )
    start(buffer)

    await asyncio.sleep(0.3)  # several intervals

    assert database.calls == 0
    assert buffer.last_flush is None


async def test_failed_write_waits_a_full_interval(start, caplog):
    database = FlakyDatabase()
    buffer = MetricBuffer(batch_size=5, interval=0.6, session_factory=database)
    start(buffer)

    buffer.add(make_samples(5))  # size trigger, write fails
    await wait_until(lambda: database.calls == 1)
    failed_at = time.monotonic()

    # The size condition holds again, but no early retry
    buffer.add(make_samples(10, start=5))
    await asyncio.sleep(0.3)
    assert database.calls == 1
    assert len(buffer) == 15  # kept

    database.fail = False
    await wait_until(lambda: buffer.last_flush is not None)
    assert time.monotonic() - failed_at >= 0.55
    assert database.calls == 2
    assert await count_rows(Metric) == 15
    assert len(buffer) == 0

    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert "Could not write 5 metrics" in errors[0].getMessage()
    async with SessionLocal() as session:
        log = await session.scalar(
            select(SystemLog).where(SystemLog.action == "metric_flush_failed")
        )
    assert log.level == "ERROR"


async def test_full_buffer_drops_oldest(caplog):
    buffer = MetricBuffer(batch_size=100, interval=10, max_size=5)

    buffer.add(make_samples(8))

    assert len(buffer) == 5
    assert await buffer.flush("shutdown")
    async with SessionLocal() as session:
        values = (await session.scalars(select(Metric.value))).all()
    assert sorted(values) == [3, 4, 5, 6, 7]
    assert "dropped the 3 oldest" in caplog.text


async def test_shutdown_flush_writes_the_rest():
    buffer = MetricBuffer(batch_size=100, interval=10)
    buffer.add(make_samples(25))

    assert await buffer.flush("shutdown")

    assert await count_rows(Metric) == 25
    assert len(buffer) == 0
    assert buffer.last_flush.reason == "shutdown"
