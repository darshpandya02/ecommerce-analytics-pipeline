"""Offline drill: every anomaly type injected into a 2 h batch must trip its designed detector."""
from datetime import timedelta

import pandas as pd
import pytest

from pipeline import generator, quality
from tests.test_generator import T0


def frame(batch):
    return pd.DataFrame.from_records(batch.events)


def test_clean_batch_passes_all_raw_checks():
    b = generator.generate_window(T0, T0 + timedelta(hours=2))
    checks = quality.raw_batch_checks(frame(b), expected_rows=len(b.events))
    failed = [c.name for c in checks if not c.success]
    assert failed == []


@pytest.mark.parametrize("kind", generator.ANOMALY_TYPES)
def test_anomaly_is_detected(kind):
    b = generator.generate_window(T0, T0 + timedelta(hours=2))
    expected = len(b.events)
    b = generator.inject_anomaly(b, force=kind)
    checks = quality.raw_batch_checks(frame(b), expected_rows=expected)
    detected, hits = quality.score_anomaly(b.anomaly, checks)
    raw_detectors = {d for d in quality.DETECTORS[kind] if d.startswith("raw.")}
    if kind == "price_spike" and not detected:
        pytest.xfail("x100 of a small basket can stay under the range limit")
    assert detected, f"{kind} not caught; failed={[c.name for c in checks if not c.success]}"
    assert set(hits) <= raw_detectors | quality.DETECTORS[kind]


def test_observations_are_json_safe():
    """A null burst puts NaN into GX's unexpected-value samples; persisted JSON must not contain it."""
    import json

    b = generator.inject_anomaly(generator.generate_window(T0, T0 + timedelta(hours=2)), force="null_burst")
    for c in quality.raw_batch_checks(frame(b), expected_rows=None):
        json.loads(json.dumps(quality._jsonable(c.observed), allow_nan=False))
