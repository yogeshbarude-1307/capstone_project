"""Layered drift monitors (docs/10). Each monitor compares a reference window
against a monitored window and returns a statistic/p-value/effect-size triple;
``alerting.py`` combines these per its documented discipline.

Only monitors buildable from data this POC already produces are implemented.
The feature<->demand relationship (concept drift) and rolling forecast-
performance layers require joining per-origin forecast results to feature
windows and are left for follow-up work — listed in NOT_IMPLEMENTED rather
than approximated.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

import numpy as np
import pandas as pd

from dsfs.drift.detectors import (
    chi_square_categorical,
    effect_size_cohens_d,
    ks_two_sample,
    total_variation_distance,
)
from dsfs.models.signal_record import SignalRecord
from dsfs.models.source_evidence import SourceEvidence

NOT_IMPLEMENTED = {
    "feature_demand_relationship": (
        "Rolling-window correlation between a feature and subsequently realized "
        "demand requires joining per-origin forecast results to feature windows; "
        "not built in this POC. See docs/16-revised-execution-plan.md."
    ),
    "forecast_performance": (
        "Rolling MASE/bias on mature origins requires a live rolling forecast "
        "loop distinct from the batch rolling-origin CV harness; not built here."
    ),
}


@dataclass
class MonitorResult:
    layer: str
    metric: str
    statistic: float
    p_value: float
    effect_size: float


def monitor_note_length(reference_notes: list[SourceEvidence], monitored_notes: list[SourceEvidence]) -> MonitorResult:
    ref = np.array([len(n.raw_text) for n in reference_notes], dtype=float)
    mon = np.array([len(n.raw_text) for n in monitored_notes], dtype=float)
    d_stat, p_value = ks_two_sample(ref, mon)
    return MonitorResult("raw_text", "note_length", d_stat, p_value, effect_size_cohens_d(ref, mon))


def monitor_source_type_mix(reference_notes: list[SourceEvidence], monitored_notes: list[SourceEvidence]) -> MonitorResult:
    ref_counts = dict(Counter(str(n.source_type) for n in reference_notes))
    mon_counts = dict(Counter(str(n.source_type) for n in monitored_notes))
    stat, p_value = chi_square_categorical(ref_counts, mon_counts)
    return MonitorResult("raw_text", "source_type_mix", stat, p_value, total_variation_distance(ref_counts, mon_counts))


def monitor_signal_type_mix(reference_signals: list[SignalRecord], monitored_signals: list[SignalRecord]) -> MonitorResult:
    ref_counts = dict(Counter(str(s.signal_type) for s in reference_signals))
    mon_counts = dict(Counter(str(s.signal_type) for s in monitored_signals))
    stat, p_value = chi_square_categorical(ref_counts, mon_counts)
    return MonitorResult("extraction", "signal_type_mix", stat, p_value, total_variation_distance(ref_counts, mon_counts))


def monitor_feature_numeric(column: str, reference_d3: pd.DataFrame, monitored_d3: pd.DataFrame) -> MonitorResult:
    ref = reference_d3[column].dropna().astype(float).to_numpy() if column in reference_d3.columns else np.array([])
    mon = monitored_d3[column].dropna().astype(float).to_numpy() if column in monitored_d3.columns else np.array([])
    d_stat, p_value = ks_two_sample(ref, mon)
    return MonitorResult("features", column, d_stat, p_value, effect_size_cohens_d(ref, mon))


def count_pit_violations(
    d3: pd.DataFrame,
    signals_by_id: dict[str, SignalRecord],
    sources: dict[str, SourceEvidence],
) -> int:
    """Hard invariant, always immediate (docs/10): no contributing signal's
    source may have become available after the row's forecast_cutoff. D3
    rows already passed the PIT filter at build time (features/transformer.py),
    so this is a re-check, not the primary enforcement — a nonzero count means
    that filter itself regressed, not ordinary drift. Rows whose
    contributing_signal_ids don't resolve are skipped (a lineage-completeness
    problem, reported separately by dsfs.lineage), not counted as violations.
    """
    if "forecast_cutoff" not in d3.columns or "contributing_signal_ids" not in d3.columns:
        return 0
    cutoffs = pd.to_datetime(d3["forecast_cutoff"], utc=True)
    violations = 0
    for cutoff, signal_ids in zip(cutoffs, d3["contributing_signal_ids"]):
        for sid in signal_ids:
            record = signals_by_id.get(sid)
            if record is None:
                continue
            source = sources.get(record.source_id)
            if source is None:
                continue
            if source.available_at > cutoff:
                violations += 1
    return violations
