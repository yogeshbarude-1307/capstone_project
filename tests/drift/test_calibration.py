"""No-drift-window calibration (docs/10): measure a monitor's own false-alert
rate before trusting it against a seeded-drift window."""

from __future__ import annotations

import random

from dsfs.drift.calibration import calibrate_false_alert_rate, split_into_no_drift_windows
from dsfs.drift.monitors import MonitorResult


def _stable_monitor(reference, monitored) -> MonitorResult:
    """A monitor that never actually differs — pure-noise p-values should be
    uniform, so false-alert rate should land near alpha (0.05), not near 0 or 1."""
    rng = random.Random(hash((tuple(reference), tuple(monitored))) & 0xFFFFFFFF)
    return MonitorResult("test", "noise", 0.0, rng.random(), 0.0)


def test_false_alert_rate_near_alpha_for_pure_noise():
    items = list(range(400))
    pairs = split_into_no_drift_windows(items, n_pairs=200, window_size=20, seed=1)
    result = calibrate_false_alert_rate(_stable_monitor, pairs, alpha=0.05)
    assert result.n_windows == 200
    # Should land in a reasonable neighborhood of the nominal 5% rate.
    assert 0.0 <= result.false_alert_rate <= 0.15


def test_split_into_no_drift_windows_deterministic():
    items = list(range(100))
    a = split_into_no_drift_windows(items, n_pairs=5, window_size=10, seed=7)
    b = split_into_no_drift_windows(items, n_pairs=5, window_size=10, seed=7)
    assert a == b


def test_split_into_no_drift_windows_empty_when_too_few_items():
    assert split_into_no_drift_windows(list(range(5)), n_pairs=3, window_size=10) == []


def test_calibrate_empty_pairs_returns_nan_rate():
    result = calibrate_false_alert_rate(_stable_monitor, [])
    assert result.n_windows == 0
    import math
    assert math.isnan(result.false_alert_rate)
