"""Regression test: signal_features.forecast_cutoff arrives as an ISO string
(from ForecastFeatureRecord.model_dump(mode="json")), while D0.period_start
is a plain datetime.date. Before normalize_cutoff_column, the merge in
run_arm silently matched zero rows for every real (non-fixture) run, making
arms B/C/D numerically identical to arm A.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from dsfs.forecast.harness import (
    ForecastConfig,
    _merge_signal_features,
    normalize_cutoff_column,
    run_arm,
)


def _make_d0_with_date_period_start(n_weeks: int = 80) -> pd.DataFrame:
    """Mirrors real D0: period_start is datetime.date, not pd.Timestamp."""
    rows = []
    for w in range(n_weeks):
        rows.append({
            "entity_key": "CUST-0001",
            "period_start": date(2023, 1, 2) + pd.Timedelta(weeks=w).to_pytimedelta(),
            "week_index": w,
            "demand": 100.0 + 5.0 * np.sin(2 * np.pi * w / 52),
        })
    return pd.DataFrame(rows)


def _make_iso_string_signal_features(d0: pd.DataFrame) -> pd.DataFrame:
    """Mirrors real oracle.py / access.py output: forecast_cutoff is an ISO string."""
    rows = []
    for _, row in d0.iterrows():
        cutoff_iso = pd.Timestamp(row["period_start"]).tz_localize("UTC").isoformat()
        rows.append({
            "entity_key": row["entity_key"],
            "forecast_cutoff": cutoff_iso,
            "has_active_signal_30d": True,
            "signal_count_30d": 3,
            "net_demand_direction_30d": "INCREASE",
            "expected_qty_delta_next_horizon": 50.0,
            "committed_qty": None,
            "cancelled_qty_30d": None,
            "delay_count_90d": 0,
            "nearest_effective_start_days": None,
            "days_since_latest_signal": 2,
            "independent_source_count_30d": 1,
            "active_conflict_count": 0,
        })
    return pd.DataFrame(rows)


def test_iso_string_cutoff_actually_merges_with_date_period_start():
    """This is the exact real-world dtype pairing: string vs datetime.date.

    Uses _merge_signal_features directly (not a full run_arm/ridge round trip)
    because a signal that is constant across the whole training window has
    zero effect on a centered ridge fit regardless of whether the merge
    worked — that would be a false negative for this specific regression.
    """
    d0 = _make_d0_with_date_period_start()
    signal_features = _make_iso_string_signal_features(d0)
    assert not pd.api.types.is_datetime64_any_dtype(signal_features["forecast_cutoff"])  # strings, as in real oracle.py output

    normalized = normalize_cutoff_column(signal_features)
    entity_row = d0.iloc[10]
    cutoff_date = pd.Timestamp(entity_row["period_start"])  # what run_arm now normalizes dates[t] to

    merged = _merge_signal_features({"lag_1": 1.0}, normalized, entity_row["entity_key"], cutoff_date)
    assert merged.get("signal_count_30d") == 3.0
    assert merged.get("expected_qty_delta_next_horizon") == 50.0

    # And confirm the unnormalized (string) column fails to merge, proving the
    # normalization step is actually load-bearing, not a no-op.
    unmerged = _merge_signal_features({"lag_1": 1.0}, signal_features, entity_row["entity_key"], cutoff_date)
    assert "signal_count_30d" not in unmerged


def test_normalize_cutoff_column_produces_comparable_dtype():
    df = pd.DataFrame({"forecast_cutoff": ["2023-01-02T00:00:00+00:00", "2023-01-09T00:00:00+00:00"]})
    normalized = normalize_cutoff_column(df)
    assert pd.api.types.is_datetime64_any_dtype(normalized["forecast_cutoff"])
    assert normalized["forecast_cutoff"].iloc[0] == pd.Timestamp("2023-01-02")


def test_normalize_cutoff_column_passthrough_on_empty_or_none():
    assert normalize_cutoff_column(None) is None
    empty = pd.DataFrame({"forecast_cutoff": []})
    assert normalize_cutoff_column(empty) is empty
