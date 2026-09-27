"""Multi-horizon forecasts must differ by horizon, not repeat one one-step prediction H times.

Regression test for the bug where ``pred_feats`` was computed once at
``origin_idx`` (independent of ``h``) and the same trained model/features were
reused for every horizon step, producing identical predictions across horizons.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from dsfs.forecast.harness import ForecastConfig, run_arm


def _make_trending_d0(n_weeks: int = 80) -> pd.DataFrame:
    """A single entity with a clear linear trend, so different horizons should
    predict measurably different demand levels."""
    rows = []
    for w in range(n_weeks):
        demand = 100.0 + 2.0 * w  # steep, noise-free trend
        rows.append({
            "entity_key": "CUST-0001",
            "period_start": pd.Timestamp("2023-01-02") + pd.Timedelta(weeks=w),
            "week_index": w,
            "demand": demand,
        })
    return pd.DataFrame(rows)


def test_predictions_vary_by_horizon_on_trending_series():
    d0 = _make_trending_d0()
    config = ForecastConfig(train_weeks=40, horizon_weeks=4, min_origins=5)
    result = run_arm(d0, config, "A", signal_features=None)

    by_origin: dict[int, dict[int, float]] = {}
    for o in result.origins:
        by_origin.setdefault(o.origin_week_index, {})[o.horizon_week_index] = o.predicted

    origins_with_full_horizon = {
        origin: preds for origin, preds in by_origin.items() if len(preds) == config.horizon_weeks
    }
    assert origins_with_full_horizon, "expected at least one origin with all horizons populated"

    origin, preds = next(iter(origins_with_full_horizon.items()))
    values = [preds[h] for h in sorted(preds)]
    assert len(set(values)) > 1, (
        f"predictions identical across horizons at origin {origin}: {values} — "
        "multi-horizon regression: same one-step model/features reused for every h"
    )
    # On a rising trend, later horizons should predict higher demand.
    assert values == sorted(values), f"expected increasing predictions on rising trend: {values}"


def test_each_horizon_trained_on_strictly_past_target_pairs():
    """No training pair may use a target at or after the forecast origin."""
    d0 = _make_trending_d0(n_weeks=60)
    config = ForecastConfig(train_weeks=30, horizon_weeks=3, min_origins=5)
    result = run_arm(d0, config, "A", signal_features=None)
    assert len(result.origins) > 0
    for o in result.origins:
        assert o.horizon_week_index > o.origin_week_index
