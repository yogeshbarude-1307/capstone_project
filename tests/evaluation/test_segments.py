"""Segmentation helpers for M9 (docs/08): per-horizon and signal-exposed subsets."""

from __future__ import annotations

import pandas as pd

from dsfs.evaluation.segments import per_horizon, signal_exposed_subset
from dsfs.forecast.harness import OriginResult


def _origin(entity="CUST-0001", origin_week=10, horizon_week=12, cutoff="2023-03-13", arm="A"):
    return OriginResult(
        entity_key=entity,
        origin_week_index=origin_week,
        horizon_week_index=horizon_week,
        actual=100.0,
        predicted=95.0,
        arm=arm,
        origin_cutoff=pd.Timestamp(cutoff),
    )


def test_per_horizon_groups_by_horizon_step():
    origins = [
        _origin(origin_week=10, horizon_week=11),  # h=1
        _origin(origin_week=10, horizon_week=12),  # h=2
        _origin(origin_week=20, horizon_week=21),  # h=1
    ]
    grouped = per_horizon(origins)
    assert set(grouped) == {1, 2}
    assert len(grouped[1]) == 2
    assert len(grouped[2]) == 1


def test_per_horizon_empty_input():
    assert per_horizon([]) == {}


def test_signal_exposed_subset_exact_match_on_entity_and_cutoff():
    origins = [
        _origin(entity="CUST-0001", cutoff="2023-01-02"),
        _origin(entity="CUST-0002", cutoff="2023-01-02"),
        _origin(entity="CUST-0001", cutoff="2023-01-09"),
    ]
    signal_features = pd.DataFrame([
        {"entity_key": "CUST-0001", "forecast_cutoff": "2023-01-02T00:00:00+00:00", "has_active_signal_30d": True},
        {"entity_key": "CUST-0002", "forecast_cutoff": "2023-01-02T00:00:00+00:00", "has_active_signal_30d": False},
    ])
    exposed = signal_exposed_subset(origins, signal_features)
    assert len(exposed) == 1
    assert exposed[0].entity_key == "CUST-0001"
    assert exposed[0].origin_cutoff == pd.Timestamp("2023-01-02")


def test_signal_exposed_subset_empty_when_no_signal_features():
    origins = [_origin()]
    assert signal_exposed_subset(origins, None) == []
    assert signal_exposed_subset(origins, pd.DataFrame()) == []


def test_signal_exposed_subset_excludes_cutoffs_without_active_signal():
    origins = [_origin(cutoff="2023-01-02"), _origin(cutoff="2023-01-09")]
    signal_features = pd.DataFrame([
        {"entity_key": "CUST-0001", "forecast_cutoff": "2023-01-02T00:00:00+00:00", "has_active_signal_30d": True},
        {"entity_key": "CUST-0001", "forecast_cutoff": "2023-01-09T00:00:00+00:00", "has_active_signal_30d": False},
    ])
    exposed = signal_exposed_subset(origins, signal_features)
    assert len(exposed) == 1
    assert exposed[0].origin_cutoff == pd.Timestamp("2023-01-02")
