"""In-memory metric buffer, written to the database in batches.

A batch is written when BATCH_INTERVAL_SECONDS have passed (reason
"interval") or as soon as BATCH_SIZE metrics are waiting (reason "size").
"""

import asyncio
import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.base import utc_now
from app.db.session import SessionLocal
from app.models import LogLevel, Metric
from app.schemas.metric import MetricSample
from app.services import audit_service

logger = logging.getLogger(__name__)

# Upper bound while the database is down: about 18 minutes of default data
MAX_BUFFERED = 10_000

FlushReason = Literal["interval", "size", "shutdown"]


@dataclass(frozen=True)
class FlushInfo:
    """The last successful batch write, shown by the database status API."""

    at: datetime
    count: int
    reason: FlushReason


class MetricBuffer:
    def __init__(
        self,
        batch_size: int,
        interval: float,
        max_size: int = MAX_BUFFERED,
        session_factory: Callable[[], AsyncSession] = SessionLocal,
    ) -> None:
        self.batch_size = batch_size
        self.interval = interval
        self.max_size = max_size
        self.session_factory = session_factory
        self.last_flush: FlushInfo | None = None
        self._items: list[MetricSample] = []
        # Set when batch_size metrics are waiting; wakes the writer early
        self._full = asyncio.Event()

    def __len__(self) -> int:
        return len(self._items)

    def add(self, samples: Iterable[MetricSample]) -> None:
        self._items.extend(samples)
        self._drop_oldest()
        if len(self._items) >= self.batch_size:
            self._full.set()

    def _drop_oldest(self) -> None:
        overflow = len(self._items) - self.max_size
        if overflow > 0:
            del self._items[:overflow]
            logger.warning(
                "Metric buffer is full: dropped the %d oldest metrics",
                overflow,
            )

    async def flush(self, reason: FlushReason) -> bool:
        """Write everything waiting in one transaction.

        Returns False when the write failed; the metrics are then put back
        at the front of the buffer. An empty buffer writes nothing.
        """
        if not self._items:
            return True
        items, self._items = self._items, []
        try:
            async with self.session_factory() as session:
                session.add_all(
                    Metric(**item.model_dump(exclude={"unit"}))
                    for item in items
                )
                await session.commit()
        except asyncio.CancelledError:
            # Stopped mid-write (shutdown): keep the data for the final flush
            self._restore(items)
            raise
        except Exception as exc:  # noqa: BLE001
            # Deliberately broad: whatever the failure, keep the data; the
            # traceback is left out, as this repeats every interval
            self._restore(items)
            logger.error(
                "Could not write %d metrics, retrying in %ss: %s",
                len(items),
                self.interval,
                exc,
            )
            await audit_service.log(
                "metric_flush_failed",
                f"Could not write {len(items)} metrics: "
                f"{type(exc).__name__}: {exc}",
                level=LogLevel.ERROR,
            )
            return False
        self.last_flush = FlushInfo(
            at=utc_now(), count=len(items), reason=reason
        )
        logger.info("Wrote %d metrics (%s)", len(items), reason)
        return True

    def _restore(self, items: list[MetricSample]) -> None:
        # Older data goes back in front of anything added meanwhile
        self._items[:0] = items
        self._drop_oldest()

    async def _wait_for_trigger(self) -> FlushReason:
        try:
            await asyncio.wait_for(self._full.wait(), timeout=self.interval)
            reason = "size"
        except TimeoutError:
            reason = "interval"
        # Cleared on every wake-up, whatever woke us
        self._full.clear()
        return reason

    async def run(self) -> None:
        """Background task writing batches until cancelled."""
        while True:
            reason = await self._wait_for_trigger()
            while not await self.flush(reason):
                # The database is failing: retry once per interval and
                # ignore the size trigger meanwhile, instead of retrying
                # every second
                await asyncio.sleep(self.interval)
                reason = "interval"


metric_buffer = MetricBuffer(
    batch_size=settings.batch_size, interval=settings.batch_interval_seconds
)
