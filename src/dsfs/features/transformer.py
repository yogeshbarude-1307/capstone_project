"""Point-in-time feature transformation from signal ledger to ForecastFeatureRecord.

Implements the PIT eligibility rule from docs/03-data-model.md:
  signal.available_at <= cutoff
  AND [effective_start, effective_end] intersects the forecast horizon
  AND signal.record_status == ACTIVE

The forecast horizon is [cutoff, cutoff + horizon_days). Signals without
effective dates are included when they have available_at within the lookback
window — they contribute to presence/direction/recency features but not to
magnitude or timing features that require dated claims.

Percentages and quantities stay separate: magnitude_basis == PERCENT contributes
to expected_qty_delta_next_horizon only when a baseline is available (not in this
POC), so percent-based magnitudes are excluded from quantity sums.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import NamedTuple

from dsfs.features.direction import direction_vote as _direction_vote
from dsfs.models.common import as_utc
from dsfs.models.forecast_feature import (
    ForecastFeatureRecord,
    NetDemandDirection,
    StalenessStatus,
)
from dsfs.models.signal_record import (
    BusinessCertainty,
    Direction,
    MagnitudeBasis,
    RecordStatus,
    SignalRecord,
    SignalType,
    ValidationStatus,
)

DEFAULT_FEATURE_DEFINITION_VERSION = "fdv-0.1.0"
DEFAULT_LOOKBACK_DAYS = 30
DEFAULT_HORIZON_DAYS = 28
DEFAULT_STALENESS_THRESHOLD_DAYS = 14
LONG_LOOKBACK_DAYS = 90


class CutoffSpec(NamedTuple):
    entity_key: str
    forecast_cutoff: datetime


def _is_pit_eligible(
    signal: SignalRecord,
    available_at: datetime,
    cutoff: datetime,
) -> bool:
    """PIT gate: the signal's source must have been available at the cutoff."""
    return available_at <= cutoff


def _intersects_horizon(
    signal: SignalRecord,
    horizon_start: datetime,
    horizon_end: datetime,
) -> bool:
    """Check whether the signal's effective period intersects [horizon_start, horizon_end).

    Signals with no effective dates pass this check — they are undated claims
    and are included for presence/direction but excluded from timing features.
    """
    if signal.effective_start is None and signal.effective_end is None:
        return True
    eff_start = signal.effective_start or horizon_start
    eff_end = signal.effective_end or horizon_end
    return eff_start < horizon_end and eff_end > horizon_start


def _is_actionable(signal: SignalRecord) -> bool:
    return (
        signal.record_status == RecordStatus.ACTIVE
        and signal.validation_status in (ValidationStatus.PASS, ValidationStatus.REVIEW)
        and signal.signal_type != SignalType.NO_SIGNAL
    )


def _resolve_net_direction(votes: list[int]) -> NetDemandDirection:
    if not votes:
        return NetDemandDirection.UNKNOWN
    total = sum(votes)
    has_up = any(v > 0 for v in votes)
    has_down = any(v < 0 for v in votes)
    if has_up and has_down:
        return NetDemandDirection.MIXED
    if total > 0:
        return NetDemandDirection.INCREASE
    if total < 0:
        return NetDemandDirection.DECREASE
    return NetDemandDirection.STABLE


def build_feature_row(
    entity_key: str,
    cutoff: datetime,
    eligible_signals: list[SignalRecord],
    source_available_at: dict[str, datetime],
    *,
    generated_at: datetime | None = None,
    feature_definition_version: str = DEFAULT_FEATURE_DEFINITION_VERSION,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    horizon_days: int = DEFAULT_HORIZON_DAYS,
    staleness_threshold_days: int = DEFAULT_STALENESS_THRESHOLD_DAYS,
) -> ForecastFeatureRecord:
    """Build one ForecastFeatureRecord for (entity_key, cutoff).

    ``eligible_signals`` must already be filtered to ACTIVE, PIT-eligible,
    horizon-intersecting signals for this entity. ``source_available_at`` maps
    source_id -> available_at for recency/staleness calculations.
    """
    cutoff = as_utc(cutoff)
    now = generated_at or datetime.now(timezone.utc)
    lookback_start = cutoff - timedelta(days=lookback_days)
    long_lookback_start = cutoff - timedelta(days=LONG_LOOKBACK_DAYS)
    horizon_start = cutoff
    horizon_end = cutoff + timedelta(days=horizon_days)

    signals_30d = [
        s for s in eligible_signals
        if source_available_at[s.source_id] > lookback_start
    ]

    contributing_ids = [s.signal_id for s in eligible_signals]

    has_active = len(signals_30d) > 0
    count_30d = len(signals_30d)

    direction_votes = [_direction_vote(s.direction, s.negated) for s in signals_30d]
    net_direction = _resolve_net_direction(direction_votes)

    qty_delta = 0.0
    has_qty = False
    committed = 0.0
    has_committed = False
    cancelled = 0.0
    has_cancelled = False
    for s in signals_30d:
        if s.magnitude_value is not None and s.magnitude_basis != MagnitudeBasis.PERCENT:
            if s.record_status == RecordStatus.ACTIVE:
                if s.signal_type == SignalType.ORDER_LIFECYCLE and s.direction == Direction.DECREASE:
                    cancelled += abs(s.magnitude_value)
                    has_cancelled = True
                elif s.business_certainty in (BusinessCertainty.ASSERTED, BusinessCertainty.EXPECTED):
                    committed += abs(s.magnitude_value)
                    has_committed = True
                vote = _direction_vote(s.direction, s.negated)
                qty_delta += s.magnitude_value * vote if vote != 0 else 0
                has_qty = True

    delay_count = 0
    for s in eligible_signals:
        if (
            source_available_at[s.source_id] > long_lookback_start
            and s.signal_type == SignalType.TIMING_REVISION
            and s.direction == Direction.DECREASE
        ):
            delay_count += 1

    nearest_eff_days: int | None = None
    for s in eligible_signals:
        if s.effective_start is not None and s.effective_start >= cutoff:
            delta = int((s.effective_start - cutoff).total_seconds() / 86400)
            if nearest_eff_days is None or delta < nearest_eff_days:
                nearest_eff_days = delta

    latest_available: datetime | None = None
    for s in eligible_signals:
        avail = source_available_at[s.source_id]
        if latest_available is None or avail > latest_available:
            latest_available = avail
    days_since_latest: int | None = None
    if latest_available is not None:
        days_since_latest = max(0, int((cutoff - latest_available).total_seconds() / 86400))

    source_ids_30d = {s.source_id for s in signals_30d}
    independent_count = len(source_ids_30d)

    conflict_count = 0
    directions_by_type: dict[str, set[int]] = {}
    for s in signals_30d:
        vote = _direction_vote(s.direction, s.negated)
        if vote != 0:
            key = s.signal_type.value
            directions_by_type.setdefault(key, set()).add(vote)
    for dirs in directions_by_type.values():
        if len(dirs) > 1:
            conflict_count += 1

    staleness = StalenessStatus.UNKNOWN
    if days_since_latest is not None:
        staleness = (
            StalenessStatus.FRESH
            if days_since_latest <= staleness_threshold_days
            else StalenessStatus.STALE
        )

    return ForecastFeatureRecord(
        entity_key=entity_key,
        forecast_cutoff=cutoff,
        feature_definition_version=feature_definition_version,
        generated_at=now,
        contributing_signal_ids=contributing_ids,
        has_active_signal_30d=has_active,
        signal_count_30d=count_30d,
        net_demand_direction_30d=net_direction,
        expected_qty_delta_next_horizon=qty_delta if has_qty else None,
        committed_qty=committed if has_committed else None,
        cancelled_qty_30d=cancelled if has_cancelled else None,
        delay_count_90d=delay_count,
        nearest_effective_start_days=nearest_eff_days,
        days_since_latest_signal=days_since_latest,
        independent_source_count_30d=independent_count,
        active_conflict_count=conflict_count,
        feature_available_at=now,
        staleness_status=staleness,
    )


def select_eligible_signals(
    signals: list[SignalRecord],
    entity_key: str,
    cutoff: datetime,
    source_available_at: dict[str, datetime],
    *,
    horizon_days: int = DEFAULT_HORIZON_DAYS,
) -> list[SignalRecord]:
    """Filter signals to those eligible for (entity_key, cutoff)."""
    cutoff = as_utc(cutoff)
    horizon_start = cutoff
    horizon_end = cutoff + timedelta(days=horizon_days)
    result = []
    for s in signals:
        if s.forecast_key != entity_key:
            continue
        if not _is_actionable(s):
            continue
        avail = source_available_at.get(s.source_id)
        if avail is None:
            continue
        if not _is_pit_eligible(s, avail, cutoff):
            continue
        if not _intersects_horizon(s, horizon_start, horizon_end):
            continue
        result.append(s)
    return result
