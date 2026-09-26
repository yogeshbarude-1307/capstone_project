"""Tests for the PIT feature transformer (Milestone 5).

Covers the test families from docs/11-testing-strategy.md:
- Temporal / leakage: PIT eligibility, future-available exclusion,
  future-effective-but-available inclusion
- Feature aggregation: window boundaries, direction votes, conflicts,
  magnitude handling, staleness
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from dsfs.features.transformer import (
    build_feature_row,
    select_eligible_signals,
    DEFAULT_HORIZON_DAYS,
    DEFAULT_LOOKBACK_DAYS,
)
from dsfs.models.signal_record import (
    BusinessCertainty,
    Direction,
    MagnitudeBasis,
    RecordStatus,
    SignalType,
    ValidationStatus,
)
from dsfs.models.forecast_feature import NetDemandDirection, StalenessStatus
from tests.features.conftest import make_signal, make_source, utc


CUTOFF = utc("2026-02-03T00:00:00")


class TestPITEligibility:
    """PIT eligibility rule from docs/03: available_at <= cutoff."""

    def test_signal_available_before_cutoff_is_eligible(self):
        sig = make_signal("s1", "src-1")
        src = make_source("src-1", available_at="2026-02-02T00:00:00Z")
        result = select_eligible_signals(
            [sig], "CUST-0001", CUTOFF, {src.source_id: src.available_at}
        )
        assert len(result) == 1

    def test_signal_available_at_cutoff_is_eligible(self):
        sig = make_signal("s1", "src-1")
        src = make_source("src-1", available_at="2026-02-03T00:00:00Z")
        result = select_eligible_signals(
            [sig], "CUST-0001", CUTOFF, {src.source_id: src.available_at}
        )
        assert len(result) == 1

    def test_signal_available_after_cutoff_excluded(self):
        """Adversarial PIT test from docs/11: available_at > cutoff must be absent."""
        sig = make_signal("s1", "src-1")
        src = make_source("src-1", available_at="2026-02-04T00:00:00Z")
        result = select_eligible_signals(
            [sig], "CUST-0001", CUTOFF, {src.source_id: src.available_at}
        )
        assert len(result) == 0

    def test_future_effective_but_available_in_time_included(self):
        """docs/11: effective_start after cutoff but available_at before cutoff IS included."""
        sig = make_signal(
            "s1", "src-1",
            effective_start="2026-02-10T00:00:00",
            effective_end="2026-02-20T00:00:00",
        )
        src = make_source("src-1", available_at="2026-02-01T00:00:00Z")
        result = select_eligible_signals(
            [sig], "CUST-0001", CUTOFF, {src.source_id: src.available_at}
        )
        assert len(result) == 1

    def test_superseded_signal_excluded(self):
        sig = make_signal("s1", "src-1", record_status=RecordStatus.SUPERSEDED)
        src = make_source("src-1", available_at="2026-02-01T00:00:00Z")
        result = select_eligible_signals(
            [sig], "CUST-0001", CUTOFF, {src.source_id: src.available_at}
        )
        assert len(result) == 0

    def test_no_signal_type_excluded(self):
        sig = make_signal(
            "s1", "src-1",
            signal_type=SignalType.NO_SIGNAL,
            direction=Direction.NA,
        )
        src = make_source("src-1", available_at="2026-02-01T00:00:00Z")
        result = select_eligible_signals(
            [sig], "CUST-0001", CUTOFF, {src.source_id: src.available_at}
        )
        assert len(result) == 0

    def test_wrong_entity_excluded(self):
        sig = make_signal("s1", "src-1", entity_key="CUST-0002")
        src = make_source("src-1", available_at="2026-02-01T00:00:00Z")
        result = select_eligible_signals(
            [sig], "CUST-0001", CUTOFF, {src.source_id: src.available_at}
        )
        assert len(result) == 0

    def test_effective_period_outside_horizon_excluded(self):
        """Signal whose effective period is entirely before the horizon."""
        sig = make_signal(
            "s1", "src-1",
            effective_start="2025-12-01T00:00:00",
            effective_end="2025-12-15T00:00:00",
        )
        src = make_source("src-1", available_at="2026-02-01T00:00:00Z")
        result = select_eligible_signals(
            [sig], "CUST-0001", CUTOFF, {src.source_id: src.available_at}
        )
        assert len(result) == 0


class TestFeatureAggregation:
    """Feature aggregation: direction, magnitude, conflict, staleness."""

    def _build(self, signals, sources, **kwargs):
        avail = {s.source_id: sources[s.source_id].available_at for s in signals}
        return build_feature_row(
            "CUST-0001", CUTOFF, signals, avail,
            generated_at=CUTOFF, **kwargs,
        )

    def test_empty_signals_produce_zero_features(self):
        row = self._build([], {})
        assert row.has_active_signal_30d is False
        assert row.signal_count_30d == 0
        assert row.net_demand_direction_30d == NetDemandDirection.UNKNOWN
        assert row.expected_qty_delta_next_horizon is None
        assert row.contributing_signal_ids == []

    def test_single_increase_direction(self):
        src = make_source("src-1", available_at="2026-02-01T00:00:00Z")
        sig = make_signal("s1", "src-1")
        row = self._build([sig], {"src-1": src})
        assert row.has_active_signal_30d is True
        assert row.signal_count_30d == 1
        assert row.net_demand_direction_30d == NetDemandDirection.INCREASE

    def test_negated_increase_becomes_decrease_direction(self):
        src = make_source("src-1", available_at="2026-02-01T00:00:00Z")
        sig = make_signal("s1", "src-1", negated=True)
        row = self._build([sig], {"src-1": src})
        assert row.net_demand_direction_30d == NetDemandDirection.DECREASE

    def test_mixed_directions(self):
        src1 = make_source("src-1", available_at="2026-02-01T00:00:00Z")
        src2 = make_source("src-2", available_at="2026-02-01T00:00:00Z")
        sig1 = make_signal("s1", "src-1", direction=Direction.INCREASE)
        sig2 = make_signal("s2", "src-2", direction=Direction.DECREASE)
        row = self._build([sig1, sig2], {"src-1": src1, "src-2": src2})
        assert row.net_demand_direction_30d == NetDemandDirection.MIXED

    def test_conflict_count(self):
        """Conflicting directions within the same signal_type counts as 1 conflict."""
        src1 = make_source("src-1", available_at="2026-02-01T00:00:00Z")
        src2 = make_source("src-2", available_at="2026-02-01T00:00:00Z")
        sig1 = make_signal("s1", "src-1", direction=Direction.INCREASE)
        sig2 = make_signal("s2", "src-2", direction=Direction.DECREASE)
        row = self._build([sig1, sig2], {"src-1": src1, "src-2": src2})
        assert row.active_conflict_count == 1

    def test_magnitude_delta_aggregation(self):
        src = make_source("src-1", available_at="2026-02-01T00:00:00Z")
        sig = make_signal(
            "s1", "src-1",
            magnitude_value=100.0,
            business_certainty=BusinessCertainty.ASSERTED,
        )
        row = self._build([sig], {"src-1": src})
        assert row.expected_qty_delta_next_horizon == 100.0
        assert row.committed_qty == 100.0

    def test_percent_magnitude_excluded_from_qty(self):
        """Percentage magnitudes don't contribute to qty_delta."""
        src = make_source("src-1", available_at="2026-02-01T00:00:00Z")
        sig = make_signal(
            "s1", "src-1",
            magnitude_value=15.0,
            magnitude_unit="%",
            magnitude_basis=MagnitudeBasis.PERCENT,
            business_certainty=BusinessCertainty.ASSERTED,
        )
        row = self._build([sig], {"src-1": src})
        assert row.expected_qty_delta_next_horizon is None

    def test_cancelled_qty_tracking(self):
        src = make_source("src-1", available_at="2026-02-01T00:00:00Z")
        sig = make_signal(
            "s1", "src-1",
            signal_type=SignalType.ORDER_LIFECYCLE,
            direction=Direction.DECREASE,
            magnitude_value=50.0,
        )
        row = self._build([sig], {"src-1": src})
        assert row.cancelled_qty_30d == 50.0

    def test_delay_count_90d(self):
        src = make_source("src-1", available_at="2026-01-15T00:00:00Z")
        sig = make_signal(
            "s1", "src-1",
            signal_type=SignalType.TIMING_REVISION,
            direction=Direction.DECREASE,
        )
        row = self._build([sig], {"src-1": src})
        assert row.delay_count_90d == 1

    def test_nearest_effective_start_days(self):
        src = make_source("src-1", available_at="2026-02-01T00:00:00Z")
        sig = make_signal(
            "s1", "src-1",
            effective_start="2026-02-10T00:00:00",
            effective_end="2026-02-20T00:00:00",
        )
        row = self._build([sig], {"src-1": src})
        assert row.nearest_effective_start_days == 7

    def test_days_since_latest_signal(self):
        src = make_source("src-1", available_at="2026-02-01T00:00:00Z")
        sig = make_signal("s1", "src-1")
        row = self._build([sig], {"src-1": src})
        assert row.days_since_latest_signal == 2

    def test_independent_source_count(self):
        src1 = make_source("src-1", available_at="2026-02-01T00:00:00Z")
        src2 = make_source("src-2", available_at="2026-02-01T00:00:00Z")
        sig1 = make_signal("s1", "src-1")
        sig2 = make_signal("s2", "src-2")
        row = self._build([sig1, sig2], {"src-1": src1, "src-2": src2})
        assert row.independent_source_count_30d == 2

    def test_staleness_fresh(self):
        src = make_source("src-1", available_at="2026-01-25T00:00:00Z")
        sig = make_signal("s1", "src-1")
        row = self._build([sig], {"src-1": src})
        assert row.staleness_status == StalenessStatus.FRESH

    def test_staleness_stale(self):
        src = make_source("src-1", available_at="2026-01-01T00:00:00Z")
        sig = make_signal("s1", "src-1")
        row = self._build([sig], {"src-1": src})
        assert row.staleness_status == StalenessStatus.STALE

    def test_lookback_window_boundary(self):
        """Signal outside the 30-day lookback doesn't count for 30d features."""
        src = make_source("src-1", available_at="2026-01-01T00:00:00Z")
        sig = make_signal("s1", "src-1")
        row = self._build([sig], {"src-1": src})
        assert row.signal_count_30d == 0
        assert row.has_active_signal_30d is False
        assert len(row.contributing_signal_ids) == 1

    def test_contributing_ids_includes_all_eligible(self):
        src1 = make_source("src-1", available_at="2026-01-01T00:00:00Z")
        src2 = make_source("src-2", available_at="2026-02-01T00:00:00Z")
        sig1 = make_signal("s1", "src-1")
        sig2 = make_signal("s2", "src-2")
        row = self._build([sig1, sig2], {"src-1": src1, "src-2": src2})
        assert set(row.contributing_signal_ids) == {"s1", "s2"}


class TestSchemaConformance:
    """Every feature row must pass the forecast_feature JSON Schema contract."""

    def test_feature_row_validates(self):
        from dsfs.contracts import validate_record
        src = make_source("src-1", available_at="2026-02-01T00:00:00Z")
        sig = make_signal("s1", "src-1")
        avail = {"src-1": src.available_at}
        row = build_feature_row(
            "CUST-0001", CUTOFF, [sig], avail, generated_at=CUTOFF,
        )
        dumped = row.model_dump(mode="json")
        validate_record("forecast_feature", dumped)

    def test_empty_feature_row_validates(self):
        from dsfs.contracts import validate_record
        row = build_feature_row(
            "CUST-0001", CUTOFF, [], {}, generated_at=CUTOFF,
        )
        dumped = row.model_dump(mode="json")
        validate_record("forecast_feature", dumped)
