"""Freshness measurement (docs/10, Milestone 10).

Two distinct freshness concepts, per docs/10's monitored layers:
  - feature-layer staleness: cutoff - latest contributing signal's available_at
    (already computed per-row as ForecastFeatureRecord.days_since_latest_signal /
    staleness_status; this module aggregates it, it does not recompute it).
  - extraction-layer processing latency: extracted_at - source.available_at,
    i.e. how long the extractor took to turn an available note into a signal.
    This is genuinely new here — nothing in the existing schema aggregates it.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from dsfs.models.signal_record import SignalRecord
from dsfs.models.source_evidence import SourceEvidence


@dataclass
class FreshnessSummary:
    n: int
    mean_days: float | None
    median_days: float | None
    p95_days: float | None
    max_days: float | None


def _summarize(values: list[float]) -> FreshnessSummary:
    if not values:
        return FreshnessSummary(n=0, mean_days=None, median_days=None, p95_days=None, max_days=None)
    s = pd.Series(values, dtype=float)
    return FreshnessSummary(
        n=len(s),
        mean_days=float(s.mean()),
        median_days=float(s.median()),
        p95_days=float(s.quantile(0.95)),
        max_days=float(s.max()),
    )


def processing_latency_days(signal: SignalRecord, source: SourceEvidence) -> float:
    """extracted_at - available_at, in days. Always >= 0 for a valid run:
    a signal cannot be extracted before its source became available."""
    return (signal.extracted_at - source.available_at).total_seconds() / 86400


def summarize_processing_latency(
    signals: list[SignalRecord], sources: dict[str, SourceEvidence],
) -> FreshnessSummary:
    """Extraction-layer latency distribution across a batch of signals."""
    values = [
        processing_latency_days(s, sources[s.source_id])
        for s in signals if s.source_id in sources
    ]
    return _summarize(values)


def summarize_feature_staleness(d3: pd.DataFrame) -> dict:
    """Feature-layer staleness distribution, reusing days_since_latest_signal
    and staleness_status already computed in D3 — not recomputed here."""
    if "days_since_latest_signal" not in d3.columns:
        return {"days_since_latest_signal": _summarize([]).__dict__, "staleness_status_counts": {}}
    values = d3["days_since_latest_signal"].dropna().astype(float).tolist()
    counts = d3["staleness_status"].value_counts(dropna=False).to_dict() if "staleness_status" in d3.columns else {}
    return {
        "days_since_latest_signal": _summarize(values).__dict__,
        "staleness_status_counts": {str(k): int(v) for k, v in counts.items()},
    }
