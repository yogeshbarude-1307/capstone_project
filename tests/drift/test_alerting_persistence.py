"""Alerting discipline (docs/10): test AND effect-size, AND persistence
across >=2 windows, except PIT violations which are always immediate."""

from __future__ import annotations

from dsfs.drift.alerting import evaluate_window, pit_violation_alert, track_persistence
from dsfs.drift.monitors import MonitorResult


def _result(p_value: float, effect_size: float) -> MonitorResult:
    return MonitorResult("features", "test_metric", statistic=0.0, p_value=p_value, effect_size=effect_size)


def test_single_window_never_fires_even_if_significant():
    results = [_result(0.001, 0.9)]
    decision = track_persistence(results)
    assert decision.fired is False


def test_two_consecutive_significant_windows_fires():
    results = [_result(0.001, 0.9), _result(0.002, 0.8)]
    decision = track_persistence(results)
    assert decision.fired is True


def test_significant_then_non_significant_resets_streak():
    results = [_result(0.001, 0.9), _result(0.5, 0.1), _result(0.001, 0.9)]
    decision = track_persistence(results)
    assert decision.fired is False


def test_significant_p_value_but_small_effect_does_not_count():
    """p-value alone is not sufficient (docs/10) — must also clear the effect-size floor."""
    results = [_result(0.0001, 0.05), _result(0.0001, 0.05)]
    decision = track_persistence(results)
    assert decision.fired is False


def test_evaluate_window_requires_both_conditions():
    assert evaluate_window(_result(0.001, 0.9)) is True
    assert evaluate_window(_result(0.5, 0.9)) is False  # not significant
    assert evaluate_window(_result(0.001, 0.05)) is False  # effect too small


def test_pit_violation_always_immediate_no_persistence_needed():
    assert pit_violation_alert(1).fired is True
    assert pit_violation_alert(0).fired is False
