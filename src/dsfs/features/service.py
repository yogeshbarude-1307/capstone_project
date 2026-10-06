"""Shared oracle/extracted semantics and combined tabular feature serving."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import pandas as pd
from dsfs.contracts import validate_record
from dsfs.extraction.ledger import ledger_as_of
from dsfs.features.direction import direction_vote
from dsfs.features.publication import published_at
from dsfs.features.transformer import build_feature_row, _intersects_horizon, _resolve_net_direction
from dsfs.forecast.harness import ForecastConfig, _build_tabular_features
from dsfs.models.common import as_utc
from dsfs.models.demand_feature import DemandFeatureRecord, FEATURE_VERSION
from dsfs.models.signal_record import ValidationStatus, RecordStatus, ImpactChannel, SignalType, MagnitudeBasis

class DemandFeatureService:
    def __init__(self, d0, signals, sources, run_id, *, delays=None, forecast_config=None):
        self.d0, self.signals, self.sources, self.run_id = d0, signals, sources, run_id
        self.delays = delays or {}
        self.config = forecast_config or ForecastConfig()
        self.publications = {sid: published_at(src.available_at, self.delays.get(sid, 0)) for sid, src in sources.items()}
        self.published_sources = {sid: src.model_copy(update={"available_at": self.publications[sid]}) for sid, src in sources.items()}
        self.by_entity = {str(e): g.sort_values("week_index").reset_index(drop=True) for e, g in d0.groupby("entity_key")}
        self.entity_signals = {e: [s for s in signals if s.forecast_key == e] for e in self.by_entity}
        self._tabular = {}
        self._views = {}

    def row(self, entity, cutoff, horizon=1):
        cutoff = as_utc(cutoff)
        if entity not in self.by_entity:
            raise KeyError(f"Unknown account: {entity}")
        start, end = cutoff + timedelta(weeks=horizon-1), cutoff + timedelta(weeks=horizon)
        # Cache the last cutoff per account for its four horizon rows. Keeping
        # every historical ledger copy would grow memory with replay length.
        previous = self._views.get(entity)
        if previous is None or previous[0] != cutoff:
            previous = (cutoff, ledger_as_of(self.entity_signals[entity], self.published_sources, cutoff,
                                           extraction_run_id=self.run_id))
            self._views[entity] = previous
        visible = previous[1]
        eligible = [s for s in visible if s.record_status == RecordStatus.ACTIVE
                    and s.validation_status == ValidationStatus.PASS and s.signal_type != SignalType.NO_SIGNAL
                    and _intersects_horizon(s, start, end)
                    and (s.effective_start or s.effective_end or self.sources[s.source_id].available_at > cutoff-timedelta(days=30))]
        # Only explicit business references allow cross-note event deduplication.
        groups = {}
        for s in eligible:
            key = s.business_event_ref or s.signal_id
            if key not in groups or (self.publications[s.source_id], s.signal_id) > (
                    self.publications[groups[key].source_id], groups[key].signal_id):
                groups[key] = s
        eligible = list(groups.values())
        demand = [s for s in eligible if s.impact_channel == ImpactChannel.DEMAND]
        avail = {sid: src.available_at for sid, src in self.sources.items()}
        # The legacy aggregate supplies metadata/count fields; demand magnitudes
        # below are computed across ALL active claims intersecting this target week.
        base = build_feature_row(entity, cutoff, demand, avail).model_dump()
        pct, qty, has_pct, has_qty = 0.0, 0.0, False, False
        for s in demand:
            if s.magnitude_value is None or s.effective_start is None or s.effective_end is None:
                continue
            overlap = max(0, (min(s.effective_end, end)-max(s.effective_start, start)).total_seconds()) / (7*86400)
            value = s.magnitude_value * direction_vote(s.direction, s.negated) * overlap
            if s.magnitude_basis == MagnitudeBasis.PERCENT:
                pct += value
                has_pct = True
            else:
                qty += value
                has_qty = True
        key = entity, cutoff
        if key not in self._tabular:
            g = self.by_entity[entity]
            dates = pd.to_datetime(g.period_start, utc=True)
            index = int((dates < pd.Timestamp(cutoff)).sum())
            # Prevent positional lag errors for cutoffs outside the observed grid.
            if index < len(g) and pd.Timestamp(dates.iloc[index]) != pd.Timestamp(cutoff):
                raise ValueError("Cutoff must match an observed weekly boundary")
            if index == len(g) and cutoff != dates.iloc[-1].to_pydatetime()+timedelta(weeks=1):
                raise ValueError("Cutoff outside supported demand history")
            self._tabular[key] = _build_tabular_features(g.demand, index, self.config)
        latencies = [(self.publications[s.source_id]-avail[s.source_id]).total_seconds()/60 for s in eligible]
        latest = max((self.publications[s.source_id] for s in eligible), default=None)
        base.update(schema_version="1.0.0", feature_definition_version=FEATURE_VERSION,
                    run_id=self.run_id, horizon_step=horizon, target_start=start, target_end=end,
                    tabular_features=self._tabular[key], signed_pct_change=pct if has_pct else None,
                    active_demand_signal_count=len(demand),
                    target_demand_direction=_resolve_net_direction([direction_vote(s.direction,s.negated) for s in demand]),
                    expected_qty_delta_next_horizon=qty if has_qty else None,
                    contributing_signal_ids=[s.signal_id for s in eligible],
                    supply_signal_count=sum(s.impact_channel == ImpactChannel.FULFILLMENT for s in eligible),
                    conditional_signal_count=sum(s.conditionality.value == "CONDITIONAL" for s in demand),
                    publication_latency_minutes=max(latencies, default=None),
                    feature_available_at=latest, freshness_breach=any(v > 60 for v in latencies),
                    rejected_signal_count=sum(s.validation_status != ValidationStatus.PASS for s in visible))
        for certainty in ("ASSERTED", "EXPECTED", "LIKELY", "POSSIBLE"):
            base[certainty.lower()+"_signal_count"] = sum(s.business_certainty.value == certainty for s in demand)
        result = DemandFeatureRecord.model_validate(base)
        validate_record("demand_feature", result.model_dump(mode="json"))
        return result

    def historical(self, pairs, horizons=(1, 2, 3, 4)):
        return pd.DataFrame([self.row(e, c, h).model_dump(mode="json") for e, c in pairs for h in horizons])
