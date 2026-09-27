"""Drift scenario evaluation and report (docs/10, Milestone 10 D4).

Ties detectors -> monitors -> calibration -> alerting into one function per
scenario: detection outcome, detection latency (weeks after the known
injection week), and the calibrated false-alert rate on the matched
pre-injection window — always reported together, never latency alone.

"Lead time" per docs/10 is formally measured against *confirmed forecast
degradation*, which requires the forecast_performance monitor this POC does
not implement (see monitors.NOT_IMPLEMENTED). What's reported here is
detection latency relative to the known injection week — a real, honestly
narrower measurement, not a substitute claim.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from dsfs.config import Settings, get_settings
from dsfs.drift.alerting import DEFAULT_ALPHA, DEFAULT_MIN_EFFECT_SIZE, track_persistence
from dsfs.drift.calibration import calibrate_false_alert_rate, split_into_no_drift_windows
from dsfs.drift.monitors import MonitorResult
from dsfs.models.source_evidence import SourceEvidence
from dsfs.synth.config import GeneratorConfig


def weekly_windows(notes: list, start_date, window_weeks: int) -> dict[int, list]:
    """Group items with an ``authored_at`` datetime into consecutive
    ``window_weeks``-wide buckets, indexed by window number."""
    buckets: dict[int, list] = defaultdict(list)
    for n in notes:
        week = (n.authored_at.date() - start_date).days // 7
        buckets[week // window_weeks].append(n)
    return dict(sorted(buckets.items()))


@dataclass
class ScenarioDriftResult:
    scenario: str
    monitor_layer: str
    monitor_metric: str
    detected: bool
    detection_latency_weeks: int | None
    calibrated_false_alert_rate: float
    window_results: list[MonitorResult] = field(default_factory=list)


def evaluate_scenario(
    notes: list[SourceEvidence],
    config: GeneratorConfig,
    monitor_fn: Callable[[list, list], MonitorResult],
    *,
    window_weeks: int = 4,
    required_consecutive: int = 2,
    alpha: float = DEFAULT_ALPHA,
    min_effect_size: float = DEFAULT_MIN_EFFECT_SIZE,
    n_calibration_pairs: int = 50,
) -> ScenarioDriftResult:
    """Evaluate one monitor against one generated (scenario, inject_at_week) run."""
    windows = weekly_windows(notes, config.start_date, window_weeks)
    reference_idx = (config.drift_inject_at_week // window_weeks) - 1

    probe = monitor_fn([], [])  # cheap way to read layer/metric names without a real comparison
    if reference_idx not in windows or not windows[reference_idx]:
        return ScenarioDriftResult(config.drift_scenario, probe.layer, probe.metric, False, None, float("nan"))
    reference = windows[reference_idx]

    calib_window_size = max(len(reference) // 4, 1)
    calib_pairs = split_into_no_drift_windows(reference, n_pairs=n_calibration_pairs, window_size=calib_window_size)
    calibration = calibrate_false_alert_rate(monitor_fn, calib_pairs, alpha=alpha)

    monitored_idxs = sorted(idx for idx in windows if idx > reference_idx)
    results: list[MonitorResult] = []
    for idx in monitored_idxs:
        result = monitor_fn(reference, windows[idx])
        results.append(result)
        decision = track_persistence(
            results, required_consecutive=required_consecutive, alpha=alpha, min_effect_size=min_effect_size,
        )
        if decision.fired:
            latency_weeks = (idx - reference_idx) * window_weeks
            return ScenarioDriftResult(
                config.drift_scenario, result.layer, result.metric, True, latency_weeks,
                calibration.false_alert_rate, results,
            )
    return ScenarioDriftResult(
        config.drift_scenario, probe.layer, probe.metric, False, None,
        calibration.false_alert_rate, results,
    )


def render_report(results: list[ScenarioDriftResult]) -> str:
    lines = [
        "# Drift Detection Report (Milestone 10)",
        "",
        "Detection outcome, detection latency (weeks after the known injection "
        "week), and calibrated false-alert rate are always reported together, "
        "never latency alone (docs/10).",
        "",
        "Detection latency here is measured against the *known injection week*, "
        "not confirmed forecast-performance degradation — the forecast_performance "
        "monitor is not implemented in this POC (see dsfs.drift.monitors.NOT_IMPLEMENTED).",
        "",
        "| Scenario | Monitor | Detected | Latency (weeks) | Calibrated false-alert rate |",
        "|---|---|---|---:|---:|",
    ]
    for r in results:
        latency = str(r.detection_latency_weeks) if r.detection_latency_weeks is not None else "—"
        far = f"{r.calibrated_false_alert_rate:.1%}" if r.calibrated_false_alert_rate == r.calibrated_false_alert_rate else "N/A"
        lines.append(f"| {r.scenario} | {r.monitor_layer}/{r.monitor_metric} | {r.detected} | {latency} | {far} |")
    return "\n".join(lines)


def main(settings: Settings | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    settings = settings or get_settings()

    print("dsfs-drift-report requires a per-scenario generated corpus; see "
          "docs/16-revised-execution-plan.md for the orchestrated M11 usage. "
          "No default single-scenario run is defined for standalone invocation.")


if __name__ == "__main__":
    main()
