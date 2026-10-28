"""Simulated server metrics: one value per server and metric every second.

Each value follows a random walk that is pulled back towards a normal
level, so readings stay mostly below the thresholds; about 1% of the
values jump above the threshold so alerts show up within minutes.
"""

import asyncio
import logging
import random
from dataclasses import dataclass

from app.db.base import utc_now
from app.models import METRIC_UNITS, MetricName
from app.realtime.buffer import MetricBuffer
from app.realtime.manager import ConnectionManager
from app.schemas.metric import MetricSample

logger = logging.getLogger(__name__)

SPIKE_PROBABILITY = 0.01
# Share of the distance to the normal level recovered every second
PULL_BACK = 0.1


@dataclass(frozen=True)
class MetricProfile:
    low: float
    high: float
    normal: float  # level the walk is pulled back to
    step: float  # standard deviation of the change per second


PROFILES = {
    MetricName.cpu: MetricProfile(low=0, high=100, normal=45, step=3),
    MetricName.memory: MetricProfile(low=0, high=100, normal=60, step=1.5),
    MetricName.temperature: MetricProfile(low=20, high=110, normal=55, step=1),
}


def is_anomaly(value: float, threshold: float) -> bool:
    # Strictly greater: a value equal to the threshold is still normal
    return value > threshold


class MetricSimulator:
    def __init__(
        self,
        servers: list[str],
        thresholds: dict[MetricName, float],
        rng: random.Random | None = None,
    ) -> None:
        self.servers = servers
        self.thresholds = thresholds
        self.rng = rng or random.Random()
        # Current value of every (server, metric) pair
        self.current = {
            (server, metric): profile.normal
            for server in servers
            for metric, profile in PROFILES.items()
        }

    def _next_value(self, server: str, metric: MetricName) -> float:
        profile = PROFILES[metric]
        if self.rng.random() < SPIKE_PROBABILITY:
            # Jump above the threshold; the walk then falls back from there
            low = min(self.thresholds[metric] + 1, profile.high)
            value = self.rng.uniform(low, profile.high)
        else:
            value = self.current[server, metric]
            value += PULL_BACK * (profile.normal - value)
            value += self.rng.gauss(0, profile.step)
        value = min(max(value, profile.low), profile.high)
        self.current[server, metric] = value
        # Rounded before the threshold check, so the stored value and the
        # anomaly flag always agree
        return round(value, 1)

    def generate(self) -> list[MetricSample]:
        """One batch: every metric of every server, all with the same time."""
        # Whole seconds, matching what the DATETIME column stores
        now = utc_now().replace(microsecond=0)
        samples = []
        for server in self.servers:
            for metric in PROFILES:
                value = self._next_value(server, metric)
                threshold = self.thresholds[metric]
                samples.append(
                    MetricSample(
                        server=server,
                        metric=metric,
                        value=value,
                        unit=METRIC_UNITS[metric],
                        threshold=threshold,
                        is_anomaly=is_anomaly(value, threshold),
                        recorded_at=now,
                    )
                )
        return samples


def metrics_message(samples: list[MetricSample]) -> dict:
    """The JSON message pushed to every WebSocket client each second."""
    data = [s.model_dump(mode="json") for s in samples]
    return {
        "type": "metrics",
        "timestamp": data[0]["recorded_at"] if data else None,
        "data": data,
    }


async def run_simulator(
    simulator: MetricSimulator,
    manager: ConnectionManager,
    buffer: MetricBuffer,
) -> None:
    """Background task: generate, broadcast and buffer one batch a second."""
    loop = asyncio.get_running_loop()
    next_tick = loop.time()
    while True:
        try:
            samples = simulator.generate()
            await manager.broadcast(metrics_message(samples))
            buffer.add(samples)
        except Exception:
            # Keep the task alive; one bad second must not stop monitoring
            logger.exception("Simulator tick failed")
        # Schedule from the previous tick, so the time spent broadcasting
        # does not make the interval drift; never try to catch up on ticks
        # missed by a stalled loop
        next_tick = max(next_tick + 1, loop.time())
        await asyncio.sleep(next_tick - loop.time())
