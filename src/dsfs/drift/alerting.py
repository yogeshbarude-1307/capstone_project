"""Alerting discipline (docs/10): a statistical test alone is not sufficient
given how sample size affects significance. Require the test AND a minimum
effect-size threshold, AND persistence across >=2 consecutive monitoring
windows — except hard schema/PIT violations, which are always immediate.
"""

from __future__ import annotations

from dataclasses import dataclass

from dsfs.drift.monitors import MonitorResult

DEFAULT_ALPHA = 0.05
DEFAULT_MIN_EFFECT_SIZE = 0.3  # a small-to-medium Cohen's d / total-variation-distance floor


@dataclass
class AlertDecision:
    fired: bool
    reason: str


def evaluate_window(result: MonitorResult, *, alpha: float = DEFAULT_ALPHA, min_effect_size: float = DEFAULT_MIN_EFFECT_SIZE) -> bool:
    """Whether a single window's result clears BOTH the significance and
    effect-size bars. This is a pre-condition for firing, not itself an alert
    (persistence across windows is still required — see ``track_persistence``)."""
    return result.p_value < alpha and abs(result.effect_size) >= min_effect_size


def track_persistence(window_results: list[MonitorResult], *, required_consecutive: int = 2, **kwargs) -> AlertDecision:
    """Alert only once ``required_consecutive`` consecutive windows each clear
    the test+effect-size bar. ``window_results`` is in chronological order."""
    streak = 0
    for i, result in enumerate(window_results):
        if evaluate_window(result, **kwargs):
            streak += 1
            if streak >= required_consecutive:
                return AlertDecision(
                    fired=True,
                    reason=f"{result.layer}/{result.metric} cleared p<alpha and |effect|>=min "
                           f"for {streak} consecutive windows (ending at window {i}).",
                )
        else:
            streak = 0
    return AlertDecision(fired=False, reason="No window sequence met the persistence requirement.")


def pit_violation_alert(violation_count: int) -> AlertDecision:
    """Hard invariant: always immediate and always critical, no persistence
    requirement and no effect-size floor (docs/10)."""
    if violation_count > 0:
        return AlertDecision(fired=True, reason=f"{violation_count} PIT violation(s) — critical, immediate.")
    return AlertDecision(fired=False, reason="No PIT violations.")
