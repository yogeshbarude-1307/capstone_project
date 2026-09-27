"""Regression test: the ablation report's bootstrap lift must use the same
absolute-error baseline as the top-level arm metrics.

Bug found via a real full-scale run (docs/19): arm A's baseline errors were
passed to bootstrap_lift_ci as *signed* differences while every ablation row's
errors were *absolute* — comparing a near-zero-mean signed baseline against an
absolute-error array produced nonsensical lift percentages in the thousands
(e.g. "-2905.86%" with a [-25282%, +10271%] CI), even though the real,
correctly-computed ExperimentMetrics.incremental_lift_vs_a for the same arm
was a modest, sane single-digit-percent number.
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

from dsfs.forecast.harness import ForecastConfig, evaluate_arm, run_arm
from dsfs.forecast.pipeline import ExperimentData, _format_ablation_report


def _make_d0(n_entities: int = 3, n_weeks: int = 70) -> pd.DataFrame:
    rng = np.random.RandomState(11)
    rows = []
    for i in range(n_entities):
        entity = f"CUST-{i+1:04d}"
        for w in range(n_weeks):
            demand = 100.0 + 8.0 * np.sin(2 * np.pi * w / 52) + rng.normal(0, 4)
            rows.append({
                "entity_key": entity,
                "period_start": pd.Timestamp("2023-01-02") + pd.Timedelta(weeks=w),
                "week_index": w,
                "demand": max(0.0, demand),
            })
    return pd.DataFrame(rows)


def _make_signal_features(d0: pd.DataFrame, rng: np.random.RandomState) -> pd.DataFrame:
    rows = []
    for _, row in d0.iterrows():
        rows.append({
            "entity_key": row["entity_key"],
            "forecast_cutoff": row["period_start"],
            "has_active_signal_30d": bool(rng.random() < 0.4),
            "signal_count_30d": int(rng.randint(0, 3)),
            "net_demand_direction_30d": rng.choice(["INCREASE", "DECREASE", "STABLE"]),
            "expected_qty_delta_next_horizon": float(rng.normal(0, 10)),
            "committed_qty": None,
            "cancelled_qty_30d": None,
            "delay_count_90d": int(rng.randint(0, 2)),
            "nearest_effective_start_days": None,
            "days_since_latest_signal": int(rng.randint(0, 20)),
            "independent_source_count_30d": 1,
            "active_conflict_count": 0,
        })
    return pd.DataFrame(rows)


def test_ablation_report_full_row_lift_matches_top_level_metric():
    d0 = _make_d0()
    config = ForecastConfig(train_weeks=40, horizon_weeks=2, min_origins=1)
    rng = np.random.RandomState(3)
    signal_features = _make_signal_features(d0, rng)

    arm_a = run_arm(d0, config, "A", signal_features=None)
    arm_b = run_arm(d0, config, "B", signal_features=signal_features)
    arm_c = run_arm(d0, config, "C", signal_features=signal_features)
    arm_d = run_arm(d0, config, "D", signal_features=signal_features)

    metrics_a = evaluate_arm(arm_a)
    metrics = {
        "A": metrics_a,
        "B": evaluate_arm(arm_b, baseline_mae=metrics_a.mae),
        "C": evaluate_arm(arm_c, baseline_mae=metrics_a.mae),
        "D": evaluate_arm(arm_d, baseline_mae=metrics_a.mae),
    }
    data = ExperimentData(
        d0=d0, config=config, metrics=metrics,
        arm_results={"A": arm_a, "B": arm_b, "C": arm_c, "D": arm_d},
        oracle_features=signal_features, extracted_features=signal_features,
    )

    report = _format_ablation_report(data)

    # Extract the "full" row's lift for arm C from the report table.
    c_section = report.split("## Arm C")[1].split("## Not implemented")[0]
    full_row = [line for line in c_section.splitlines() if line.startswith("| full")][0]
    reported_lift_str = full_row.split("|")[3].strip().rstrip("%")
    reported_lift = float(reported_lift_str) / 100

    true_lift = metrics["C"].incremental_lift_vs_a
    assert abs(reported_lift - true_lift) < 0.02, (
        f"ablation report's 'full' row lift ({reported_lift:.4f}) should closely match "
        f"the independently-computed ExperimentMetrics.incremental_lift_vs_a "
        f"({true_lift:.4f}) — both describe the same unmasked arm C vs arm A comparison"
    )

    # Sanity bound: no ablation lift should ever print in the thousands of percent
    # for this dataset (the exact symptom of the signed/absolute mismatch bug).
    for pct in re.findall(r"\|\s*([+-]?\d+\.\d+)%\s*\|", report):
        assert abs(float(pct)) < 200, f"implausible lift percentage in report: {pct}%"
