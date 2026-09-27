"""evaluate_arm must raise, not silently return NaN metrics, when a config's
train_weeks/lag_weeks are too large relative to n_weeks to produce any origin.

Regression: this previously returned ExperimentMetrics(mae=NaN, mase=NaN, ...)
with a RuntimeWarning buried in stderr, which the e2e orchestrator's manifest
would have reported as a completed run with silently useless numbers.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from dsfs.forecast.harness import ArmResult, ForecastConfig, evaluate_arm, run_arm


def _make_d0(n_weeks: int) -> pd.DataFrame:
    rows = []
    for w in range(n_weeks):
        rows.append({
            "entity_key": "CUST-0001",
            "period_start": pd.Timestamp("2023-01-02") + pd.Timedelta(weeks=w),
            "week_index": w,
            "demand": 100.0,
        })
    return pd.DataFrame(rows)


def test_evaluate_arm_raises_on_zero_origins_from_undersized_config():
    """train_weeks=20 with the default lag_weeks (max lag 26) needs
    train_weeks >= ~40 before any origin has enough training pairs."""
    d0 = _make_d0(n_weeks=40)
    config = ForecastConfig(train_weeks=20, horizon_weeks=2, min_origins=1)
    arm_a = run_arm(d0, config, "A", signal_features=None)
    assert len(arm_a.origins) == 0  # confirms the undersized-config premise
    with pytest.raises(ValueError, match="zero origins"):
        evaluate_arm(arm_a)


def test_evaluate_arm_succeeds_with_adequately_sized_config():
    d0 = _make_d0(n_weeks=80)
    config = ForecastConfig(train_weeks=40, horizon_weeks=2, min_origins=1)
    arm_a = run_arm(d0, config, "A", signal_features=None)
    assert len(arm_a.origins) > 0
    metrics = evaluate_arm(arm_a)
    assert not np.isnan(metrics.mae)
