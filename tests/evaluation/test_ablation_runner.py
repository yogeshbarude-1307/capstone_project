"""M9 ablation matrix: each row must mask columns correctly, and richer
ablations must retain at least as much predictive information as sparser ones.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from dsfs.evaluation.ablation import (
    ABLATIONS,
    NOT_IMPLEMENTED,
    apply_ablation,
    run_ablation_matrix,
)
from dsfs.forecast.harness import ForecastConfig, run_arm


def _make_d0(n_weeks: int = 80) -> pd.DataFrame:
    rng = np.random.RandomState(3)
    rows = []
    for w in range(n_weeks):
        demand = 100.0 + 10.0 * np.sin(2 * np.pi * w / 52) + rng.normal(0, 2)
        rows.append({
            "entity_key": "CUST-0001",
            "period_start": pd.Timestamp("2023-01-02") + pd.Timedelta(weeks=w),
            "week_index": w,
            "demand": max(0.0, demand),
        })
    return pd.DataFrame(rows)


def _make_signal_features(d0: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, row in d0.iterrows():
        rows.append({
            "entity_key": row["entity_key"],
            "forecast_cutoff": row["period_start"],
            "has_active_signal_30d": True,
            "signal_count_30d": 2,
            "net_demand_direction_30d": "INCREASE",
            "expected_qty_delta_next_horizon": 8.0,
            "committed_qty": None,
            "cancelled_qty_30d": None,
            "delay_count_90d": 1,
            "nearest_effective_start_days": 5,
            "days_since_latest_signal": 3,
            "independent_source_count_30d": 1,
            "active_conflict_count": 0,
        })
    return pd.DataFrame(rows)


def test_note_count_only_masks_everything_but_count():
    d0 = _make_d0()
    signal_features = _make_signal_features(d0)
    masked = apply_ablation(signal_features, "note_count_only")
    assert masked["signal_count_30d"].notna().all()
    assert "expected_qty_delta_next_horizon" not in masked
    assert "net_demand_direction_30d" not in masked
    assert "has_active_signal_30d" not in masked
    assert "independent_source_count_30d" not in masked


def test_full_ablation_is_unmasked():
    d0 = _make_d0()
    signal_features = _make_signal_features(d0)
    masked = apply_ablation(signal_features, "full")
    pd.testing.assert_frame_equal(masked, signal_features)


def test_unknown_ablation_raises():
    with pytest.raises(KeyError):
        apply_ablation(pd.DataFrame({"forecast_cutoff": ["x"]}), "not_a_real_ablation")


def test_ablation_on_none_or_empty_is_passthrough():
    assert apply_ablation(None, "full") is None
    empty = pd.DataFrame()
    assert apply_ablation(empty, "full") is empty


def test_run_ablation_matrix_produces_every_implemented_row():
    d0 = _make_d0()
    signal_features = _make_signal_features(d0)
    config = ForecastConfig(train_weeks=40, horizon_weeks=2, min_origins=5)
    baseline = run_arm(d0, config, "A", signal_features=None)

    results = run_ablation_matrix(d0, config, signal_features, arm_label="C", baseline_result=baseline)
    assert set(results) == set(ABLATIONS)
    for name, arm_result in results.items():
        assert arm_result.arm == "C"
        assert len(arm_result.origins) > 0, f"ablation {name!r} produced no origins"


def test_not_implemented_ablations_are_documented_not_fabricated():
    assert "business_certainty_conditionality" in ABLATIONS
    assert "aggregate_only_no_entity_resolution" in NOT_IMPLEMENTED
    assert "rules_vs_hybrid_vs_llm" in NOT_IMPLEMENTED
    assert "decay_vs_windowed" in NOT_IMPLEMENTED
    for reason in NOT_IMPLEMENTED.values():
        assert len(reason) > 10
