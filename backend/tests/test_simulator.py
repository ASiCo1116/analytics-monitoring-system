import random

from app.models import MetricName
from app.realtime.simulator import (
    PROFILES,
    MetricSimulator,
    is_anomaly,
    metrics_message,
)

SERVERS = ["server-1", "server-2", "server-3"]
THRESHOLDS = {
    MetricName.cpu: 90,
    MetricName.memory: 90,
    MetricName.temperature: 80,
}


def make_simulator(seed: int = 1) -> MetricSimulator:
    return MetricSimulator(SERVERS, THRESHOLDS, rng=random.Random(seed))


def test_one_batch_has_every_server_and_metric():
    samples = make_simulator().generate()

    assert len(samples) == 9
    assert {(s.server, s.metric) for s in samples} == {
        (server, metric) for server in SERVERS for metric in MetricName
    }
    assert len({s.recorded_at for s in samples}) == 1
    assert samples[0].recorded_at.microsecond == 0
    units = {s.metric: s.unit for s in samples}
    assert units == {
        MetricName.cpu: "%",
        MetricName.memory: "%",
        MetricName.temperature: "°C",
    }


def test_values_stay_in_range_and_anomalies_happen():
    simulator = make_simulator()
    # About 30 minutes of data
    samples = [s for _ in range(2000) for s in simulator.generate()]

    for sample in samples:
        profile = PROFILES[sample.metric]
        assert profile.low <= sample.value <= profile.high
        assert sample.threshold == THRESHOLDS[sample.metric]
        assert sample.is_anomaly == (sample.value > sample.threshold)
        assert sample.value == round(sample.value, 1)
    anomalies = sum(s.is_anomaly for s in samples)
    # Mostly normal, but alerts show up: roughly 1% of the values
    assert 0 < anomalies < len(samples) * 0.05


def test_threshold_is_exclusive():
    assert is_anomaly(95.2, 90) is True
    assert is_anomaly(80.0, 80) is False
    assert is_anomaly(80.1, 80) is True


def test_metrics_message():
    samples = make_simulator().generate()

    message = metrics_message(samples)

    assert message["type"] == "metrics"
    assert len(message["data"]) == 9
    assert message["timestamp"].endswith("Z")
    assert message["data"][0]["recorded_at"] == message["timestamp"]
    assert set(message["data"][0]) == {
        "server",
        "metric",
        "value",
        "unit",
        "threshold",
        "is_anomaly",
        "recorded_at",
    }
