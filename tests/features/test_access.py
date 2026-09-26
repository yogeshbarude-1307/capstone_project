"""Tests for the feature access layer (Milestone 6).

Covers the test families from docs/11-testing-strategy.md:
- Local API contract: argument validation, batch behavior, versioning
- Temporal / leakage: get_historical_features never returns a row whose
  contributing signal has available_at > cutoff
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

from dsfs.features.access import FeatureBatchResponse, FeatureStore
from dsfs.features.transformer import DEFAULT_FEATURE_DEFINITION_VERSION
from dsfs.models.forecast_feature import NetDemandDirection, StalenessStatus
from tests.features.conftest import make_signal, make_source, utc


CUTOFF = utc("2026-02-03T00:00:00")


def _store(signals, sources, **kwargs):
    src_dict = {s.source_id: s for s in sources}
    return FeatureStore(signals, src_dict, **kwargs)


class TestGetFeatures:
    def test_returns_feature_batch_response(self):
        src = make_source("src-1", available_at="2026-02-01T00:00:00Z")
        sig = make_signal("s1", "src-1")
        store = _store([sig], [src])
        resp = store.get_features(["CUST-0001"], CUTOFF)
        assert isinstance(resp, FeatureBatchResponse)
        assert len(resp.features) == 1
        assert resp.features[0].entity_key == "CUST-0001"

    def test_batch_multiple_entities(self):
        src = make_source("src-1", available_at="2026-02-01T00:00:00Z")
        sig1 = make_signal("s1", "src-1", entity_key="CUST-0001")
        sig2 = make_signal("s2", "src-1", entity_key="CUST-0002")
        store = _store([sig1, sig2], [src])
        resp = store.get_features(["CUST-0001", "CUST-0002"], CUTOFF)
        assert len(resp.features) == 2
        keys = {f.entity_key for f in resp.features}
        assert keys == {"CUST-0001", "CUST-0002"}

    def test_missing_entity_returns_empty_features(self):
        store = _store([], [])
        resp = store.get_features(["CUST-9999"], CUTOFF)
        assert len(resp.features) == 1
        assert resp.features[0].has_active_signal_30d is False
        assert resp.features[0].signal_count_30d == 0

    def test_version_override(self):
        store = _store([], [])
        resp = store.get_features(["CUST-0001"], CUTOFF, feature_set_version="fdv-test")
        assert resp.feature_definition_version == "fdv-test"
        assert resp.features[0].feature_definition_version == "fdv-test"


class TestGetHistoricalFeatures:
    def test_returns_dataframe(self):
        src = make_source("src-1", available_at="2026-02-01T00:00:00Z")
        sig = make_signal("s1", "src-1")
        store = _store([sig], [src])
        df = store.get_historical_features([("CUST-0001", CUTOFF)])
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 1
        assert df.iloc[0]["entity_key"] == "CUST-0001"

    def test_empty_pairs_returns_empty_dataframe(self):
        store = _store([], [])
        df = store.get_historical_features([])
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0

    def test_multiple_cutoffs_per_entity(self):
        src = make_source("src-1", available_at="2026-01-15T00:00:00Z")
        sig = make_signal("s1", "src-1")
        store = _store([sig], [src])
        cutoff_early = utc("2026-01-20T00:00:00")
        cutoff_late = utc("2026-02-10T00:00:00")
        df = store.get_historical_features([
            ("CUST-0001", cutoff_early),
            ("CUST-0001", cutoff_late),
        ])
        assert len(df) == 2

    def test_pit_leakage_impossible(self):
        """Adversarial test from docs/11: signal available after cutoff must NOT
        appear in contributing_signal_ids."""
        src_before = make_source("src-before", available_at="2026-02-01T00:00:00Z")
        src_after = make_source("src-after", available_at="2026-02-05T00:00:00Z")
        sig_before = make_signal("s-before", "src-before")
        sig_after = make_signal("s-after", "src-after")
        store = _store([sig_before, sig_after], [src_before, src_after])
        df = store.get_historical_features([("CUST-0001", CUTOFF)])
        contributing = df.iloc[0]["contributing_signal_ids"]
        assert "s-before" in contributing
        assert "s-after" not in contributing

    def test_future_effective_available_in_time_included(self):
        """docs/11: effective_start > cutoff but available_at <= cutoff IS included."""
        src = make_source("src-1", available_at="2026-02-01T00:00:00Z")
        sig = make_signal(
            "s1", "src-1",
            effective_start="2026-02-15T00:00:00",
            effective_end="2026-02-28T00:00:00",
        )
        store = _store([sig], [src])
        df = store.get_historical_features([("CUST-0001", CUTOFF)])
        contributing = df.iloc[0]["contributing_signal_ids"]
        assert "s1" in contributing

    def test_schema_valid_rows(self):
        """Every row from get_historical_features validates against the contract."""
        from dsfs.contracts import validate_record
        src = make_source("src-1", available_at="2026-02-01T00:00:00Z")
        sig = make_signal("s1", "src-1")
        store = _store([sig], [src])
        df = store.get_historical_features([("CUST-0001", CUTOFF)])
        for _, row in df.iterrows():
            record = {}
            for col in df.columns:
                val = row[col]
                if pd.isna(val) if not isinstance(val, (list, dict)) else False:
                    continue
                record[col] = val
            if isinstance(record.get("contributing_signal_ids"), list):
                record["contributing_signal_ids"] = list(record["contributing_signal_ids"])
            validate_record("forecast_feature", record)


class TestFeatureStoreLineage:
    def test_contributing_signal_ids_populated(self):
        src = make_source("src-1", available_at="2026-02-01T00:00:00Z")
        sig = make_signal("s1", "src-1")
        store = _store([sig], [src])
        resp = store.get_features(["CUST-0001"], CUTOFF)
        assert resp.features[0].contributing_signal_ids == ["s1"]

    def test_feature_available_at_populated(self):
        src = make_source("src-1", available_at="2026-02-01T00:00:00Z")
        sig = make_signal("s1", "src-1")
        store = _store([sig], [src])
        resp = store.get_features(["CUST-0001"], CUTOFF)
        assert resp.features[0].feature_available_at is not None

    def test_feature_definition_version_matches_store(self):
        store = _store([], [], feature_definition_version="fdv-custom")
        resp = store.get_features(["CUST-0001"], CUTOFF)
        assert resp.features[0].feature_definition_version == "fdv-custom"
