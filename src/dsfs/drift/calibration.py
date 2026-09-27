"""Calibrate a monitor's null/false-alarm behavior on synthetic no-drift
windows (docs/10: "calibrate every detector on synthetic no-drift windows
first, to characterize its null/false-alarm behavior before it is ever used
against a seeded-drift window").

test_monitors_layered.py's own "silent when no scenario" test found a real
single-window false positive for note_length — this module is what turns
that observation into a measured rate instead of a one-off surprise.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from dsfs.drift.monitors import MonitorResult


@dataclass
class CalibrationResult:
    n_windows: int
    false_alert_rate: float  # fraction of no-drift window pairs where p < alpha
    p_values: list[float]


def calibrate_false_alert_rate(
    monitor_fn: Callable[..., MonitorResult],
    window_pairs: list[tuple[object, object]],
    *,
    alpha: float = 0.05,
) -> CalibrationResult:
    """Run ``monitor_fn`` over a list of (reference, monitored) pairs that are
    all known-no-drift (e.g. two random halves of the same unshifted corpus),
    and report the empirical false-alert rate at threshold ``alpha``.

    ``monitor_fn`` must accept exactly (reference, monitored) positionally,
    matching every function in dsfs.drift.monitors.
    """
    p_values = [monitor_fn(ref, mon).p_value for ref, mon in window_pairs]
    if not p_values:
        return CalibrationResult(n_windows=0, false_alert_rate=float("nan"), p_values=[])
    false_alerts = sum(1 for p in p_values if p < alpha)
    return CalibrationResult(
        n_windows=len(p_values),
        false_alert_rate=false_alerts / len(p_values),
        p_values=p_values,
    )


def split_into_no_drift_windows(items: list, *, n_pairs: int, window_size: int, seed: int = 42) -> list[tuple[list, list]]:
    """Deterministically build ``n_pairs`` (reference, monitored) window pairs
    by randomly partitioning ``items`` — a stand-in for repeated no-drift
    generator runs, cheaper than regenerating the corpus n_pairs times."""
    import random

    rng = random.Random(seed)
    pairs = []
    if len(items) < 2 * window_size:
        return pairs
    for _ in range(n_pairs):
        sample = rng.sample(items, k=2 * window_size)
        pairs.append((sample[:window_size], sample[window_size:]))
    return pairs
