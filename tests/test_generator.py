from collections import Counter
from datetime import datetime, timedelta, timezone

import pytest

from pipeline import config, generator

T0 = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)


def ids(batch):
    return [e["event_id"] for e in batch.events]


def test_same_window_is_deterministic():
    a = generator.generate_window(T0, T0 + timedelta(hours=2))
    b = generator.generate_window(T0, T0 + timedelta(hours=2))
    assert ids(a) == ids(b) and len(a.events) > 50


def test_windows_partition_the_stream():
    """Splitting a window into micro-batches delivers exactly the same events."""
    whole = generator.generate_window(T0, T0 + timedelta(hours=3))
    parts = []
    t = T0
    for minutes in (7, 30, 31, 45, 67):
        parts += ids(generator.generate_window(t, t + timedelta(minutes=minutes)))
        t += timedelta(minutes=minutes)
    assert t == T0 + timedelta(hours=3)
    assert Counter(parts) == Counter(ids(whole))


def test_stream_contains_late_and_duplicate_events():
    b = generator.generate_window(T0, T0 + timedelta(hours=12))
    counts = Counter(ids(b))
    assert any(n > 1 for n in counts.values()), "expected at-least-once duplicates"
    lags = [(e["sent_at"] - e["event_time"]).total_seconds() for e in b.events]
    assert max(lags) > 1800, "expected late-arriving events"
    assert min(lags) >= 0


def test_funnel_is_plausible():
    b = generator.generate_window(config.STORE_EPOCH, config.STORE_EPOCH + timedelta(days=7))
    c = Counter(e["event_type"] for e in b.events)
    assert c["session_start"] > c["add_to_cart"] > c["checkout_started"] > c["order_placed"] > c["refund_issued"] > 0
    conv = c["order_placed"] / c["session_start"]
    assert 0.02 < conv < 0.1


@pytest.mark.parametrize("kind", generator.ANOMALY_TYPES)
def test_forced_anomaly_is_recorded(kind):
    b = generator.generate_window(T0, T0 + timedelta(hours=2))
    b = generator.inject_anomaly(b, force=kind)
    assert b.anomaly["anomaly_type"] == kind and b.anomaly["rows_affected"] > 0
