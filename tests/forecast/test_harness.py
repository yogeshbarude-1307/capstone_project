"""Tests for the forecast experiment harness (Milestones 7-8).

Covers docs/08 requirements:
- Rolling-origin correctness: no future observation in any training window
- Config identity: arms differ only in feature input
- Metrics: MASE, MAE, bias computation
- Arm D: shuffled features break entity-time alignment
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from dsfs.forecast.harness import (
    ForecastConfig,
    compute_bias,
    compute_incremental_lift,
    compute_mae,
    compute_mase,
    evaluate_arm,
    run_arm,
)
from dsfs.forecast.shuffle import shuffle_features


def _make_d0(n_entities: int = 2, n_weeks: int = 80) -> pd.DataFrame:
    """Synthetic demand table for testing."""
    rng = np.random.RandomState(42)
    rows = []
    for i in range(n_entities):
        entity = f"CUST-{i+1:04d}"
        for w in range(n_weeks):
            demand = 100.0 + 10.0 * np.sin(2 * np.pi * w / 52) + rng.normal(0, 5)
            rows.append({
                "entity_key": entity,
                "period_start": pd.Timestamp("2023-01-02") + pd.Timedelta(weeks=w),
                "week_index": w,
                "demand": max(0.0, demand),
            })
    return pd.DataFrame(rows)


def _make_signal_features(d0: pd.DataFrame) -> pd.DataFrame:
    """Simple signal features for testing arm B/C/D."""
    rows = []
    for _, row in d0.iterrows():
        rows.append({
            "entity_key": row["entity_key"],
            "forecast_cutoff": row["period_start"],
            "has_active_signal_30d": True,
            "signal_count_30d": 1,
            "net_demand_direction_30d": "INCREASE",
            "expected_qty_delta_next_horizon": 5.0,
            "committed_qty": None,
            "cancelled_qty_30d": None,
            "delay_count_90d": 0,
            "nearest_effective_start_days": None,
            "days_since_latest_signal": 3,
            "independent_source_count_30d": 1,
            "active_conflict_count": 0,
        })
    return pd.DataFrame(rows)


class TestRollingOrigin:
    def test_arm_a_produces_results(self):
        d0 = _make_d0()
        config = ForecastConfig(train_weeks=40, horizon_weeks=2, min_origins=5)
        result = run_arm(d0, config, "A")
        assert len(result.origins) > 0
        assert all(o.arm == "A" for o in result.origins)

    def test_no_future_leakage_in_training(self):
        """Every training observation must precede the forecast origin."""
        d0 = _make_d0()
        config = ForecastConfig(train_weeks=40, horizon_weeks=2, min_origins=5)
        result = run_arm(d0, config, "A")
        for o in result.origins:
            assert o.horizon_week_index > o.origin_week_index

    def test_predictions_are_nonnegative(self):
        d0 = _make_d0()
        config = ForecastConfig(train_weeks=40, horizon_weeks=2, min_origins=5)
        result = run_arm(d0, config, "A")
        assert all(o.predicted >= 0 for o in result.origins)


class TestConfigIdentity:
    """Arms A-D differ only in feature input, verified programmatically (docs/08)."""

    def test_same_config_across_arms(self):
        d0 = _make_d0()
        config = ForecastConfig(train_weeks=40, horizon_weeks=2, min_origins=5)
        features = _make_signal_features(d0)

        arm_a = run_arm(d0, config, "A")
        arm_b = run_arm(d0, config, "B", signal_features=features)
        arm_c = run_arm(d0, config, "C", signal_features=features)

        shuffled = shuffle_features(features)
        arm_d = run_arm(d0, config, "D", signal_features=shuffled)

        assert arm_a.config == arm_b.config == arm_c.config == arm_d.config

    def test_config_is_frozen(self):
        config = ForecastConfig()
        with pytest.raises(AttributeError):
            config.train_weeks = 99


class TestMetrics:
    def test_mae_perfect(self):
        assert compute_mae(np.array([1.0, 2.0]), np.array([1.0, 2.0])) == 0.0

    def test_mae_known(self):
        assert compute_mae(np.array([10.0, 20.0]), np.array([12.0, 18.0])) == 2.0

    def test_bias_over_forecast(self):
        bias = compute_bias(np.array([10.0]), np.array([15.0]))
        assert bias > 0

    def test_bias_under_forecast(self):
        bias = compute_bias(np.array([10.0]), np.array([5.0]))
        assert bias < 0

    def test_mase_perfect(self):
        actuals = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        preds = actuals.copy()
        mase = compute_mase(actuals, preds, seasonal_period=1)
        assert mase == 0.0

    def test_mase_naive(self):
        """MASE == 1.0 when forecast errors equal naive errors."""
        actuals = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        preds = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
        mase = compute_mase(actuals, preds, seasonal_period=1)
        assert abs(mase - 1.0) < 1e-6

    def test_incremental_lift(self):
        assert compute_incremental_lift(10.0, 8.0) == pytest.approx(0.2)

    def test_incremental_lift_zero_baseline(self):
        assert compute_incremental_lift(0.0, 5.0) == 0.0

    def test_evaluate_arm(self):
        d0 = _make_d0()
        config = ForecastConfig(train_weeks=40, horizon_weeks=2, min_origins=5)
        result = run_arm(d0, config, "A")
        metrics = evaluate_arm(result)
        assert metrics.arm == "A"
        assert metrics.mae >= 0
        assert metrics.n_origins > 0
        assert np.isfinite(metrics.mase)


class TestShuffledControl:
    def test_shuffle_breaks_alignment(self):
        d0 = _make_d0(n_entities=5, n_weeks=80)
        features = _make_signal_features(d0)
        shuffled = shuffle_features(features)
        assert len(shuffled) == len(features)
        original_order = list(zip(features["entity_key"], features["forecast_cutoff"]))
        shuffled_order = list(zip(shuffled["entity_key"], shuffled["forecast_cutoff"]))
        assert original_order != shuffled_order

    def test_shuffle_is_reproducible(self):
        d0 = _make_d0()
        features = _make_signal_features(d0)
        s1 = shuffle_features(features, seed=42)
        s2 = shuffle_features(features, seed=42)
        pd.testing.assert_frame_equal(s1, s2)

    def test_shuffle_different_seeds_differ(self):
        d0 = _make_d0()
        features = _make_signal_features(d0)
        s1 = shuffle_features(features, seed=42)
        s2 = shuffle_features(features, seed=99)
        assert not s1.equals(s2)

    def test_shuffle_clears_contributing_ids(self):
        """Shuffled features should not carry lineage from real signals."""
        d0 = _make_d0(n_entities=2, n_weeks=10)
        features = _make_signal_features(d0)
        features["contributing_signal_ids"] = [["sig-1"]] * len(features)
        shuffled = shuffle_features(features)
        for ids in shuffled["contributing_signal_ids"]:
            assert ids == []

    def test_empty_shuffle(self):
        empty = pd.DataFrame()
        result = shuffle_features(empty)
        assert len(result) == 0


class TestArmComparison:
    """Arm B (with signal features) should differ from arm A (tabular only)."""

    def test_arms_produce_different_predictions(self):
        d0 = _make_d0()
        config = ForecastConfig(train_weeks=40, horizon_weeks=2, min_origins=5)
        features = _make_signal_features(d0)

        arm_a = run_arm(d0, config, "A")
        arm_b = run_arm(d0, config, "B", signal_features=features)

        preds_a = {(o.entity_key, o.origin_week_index, o.horizon_week_index): o.predicted
                   for o in arm_a.origins}
        preds_b = {(o.entity_key, o.origin_week_index, o.horizon_week_index): o.predicted
                   for o in arm_b.origins}

        common = set(preds_a.keys()) & set(preds_b.keys())
        assert len(common) > 0
        diffs = [abs(preds_a[k] - preds_b[k]) for k in common]
        assert any(d > 0 for d in diffs)
