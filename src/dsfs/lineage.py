"""Lineage-trace utility (docs/10, Milestone 10): given a D3 feature row,
resolve back to every contributing signal and its source evidence.

Reuses the existing ledger/notes loading (dsfs.extraction.ledger,
dsfs.features.access) rather than a new storage layer.
"""

from __future__ import annotations

import argparse
import json
import random
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from dsfs.config import Settings, get_settings
from dsfs.extraction.ledger import read_ledger
from dsfs.models.signal_record import SignalRecord
from dsfs.models.source_evidence import SourceEvidence


@dataclass
class SignalLineage:
    """One contributing signal's provenance chain, ending at raw source text."""
    signal_id: str
    source_id: str
    source_revision: str
    extractor_version: str
    extracted_at: str
    evidence_span: str  # the exact substring the extractor cited
    raw_text: str
    authored_at: str
    available_at: str


@dataclass
class FeatureLineage:
    """Full lineage for one D3 row: every signal that fed it, in order."""
    entity_key: str
    forecast_cutoff: str
    contributing_signal_ids: list[str]
    signals: list[SignalLineage]

    @property
    def is_complete(self) -> bool:
        """True iff every contributing_signal_id resolved to a signal and a source."""
        return len(self.signals) == len(self.contributing_signal_ids)


def trace_feature_row(
    feature_row: dict,
    signals_by_id: dict[str, SignalRecord],
    sources: dict[str, SourceEvidence],
) -> FeatureLineage:
    """Resolve one D3 row's contributing_signal_ids to their full provenance chain.

    A signal_id or source_id that fails to resolve is silently dropped from
    ``signals`` (not raised) so a caller can check ``is_complete`` and report
    the gap, rather than a single bad row aborting a whole lineage sample.
    """
    signals = []
    for sid in feature_row.get("contributing_signal_ids", []):
        record = signals_by_id.get(sid)
        if record is None:
            continue
        source = sources.get(record.source_id)
        if source is None:
            continue
        span = source.raw_text[record.evidence_ref.char_start:record.evidence_ref.char_end]
        signals.append(SignalLineage(
            signal_id=record.signal_id,
            source_id=record.source_id,
            source_revision=record.source_revision,
            extractor_version=record.extractor_version,
            extracted_at=record.extracted_at.isoformat(),
            evidence_span=span,
            raw_text=source.raw_text,
            authored_at=source.authored_at.isoformat(),
            available_at=source.available_at.isoformat(),
        ))
    return FeatureLineage(
        entity_key=feature_row["entity_key"],
        forecast_cutoff=str(feature_row["forecast_cutoff"]),
        contributing_signal_ids=list(feature_row.get("contributing_signal_ids", [])),
        signals=signals,
    )


def load_lineage_inputs(
    ledger_path: Path, notes_path: Path, *, extraction_run_id: str,
) -> tuple[dict[str, SignalRecord], dict[str, SourceEvidence]]:
    raw_records = read_ledger(ledger_path)
    signals_by_id = {
        r["signal_id"]: SignalRecord.model_validate(r)
        for r in raw_records
        if r["extraction_run_id"] == extraction_run_id
    }
    with notes_path.open(encoding="utf-8") as f:
        sources = {
            (s := SourceEvidence.model_validate_json(line)).source_id: s
            for line in f if line.strip()
        }
    return signals_by_id, sources


def trace_sample(
    d3_path: Path,
    ledger_path: Path,
    notes_path: Path,
    *,
    extraction_run_id: str,
    n: int = 10,
    seed: int = 42,
) -> list[FeatureLineage]:
    """Trace a deterministic random sample of D3 rows (M11's "lineage sample")."""
    df = pd.read_parquet(d3_path)
    signals_by_id, sources = load_lineage_inputs(ledger_path, notes_path, extraction_run_id=extraction_run_id)
    with_signals = df[df["contributing_signal_ids"].apply(lambda ids: len(ids) > 0)]
    if with_signals.empty:
        return []
    rng = random.Random(seed)
    idx = rng.sample(list(with_signals.index), k=min(n, len(with_signals)))
    return [trace_feature_row(with_signals.loc[i].to_dict(), signals_by_id, sources) for i in idx]


def main(settings: Settings | None = None) -> None:
    parser = argparse.ArgumentParser(description="Trace D3 feature rows back to source evidence (Milestone 10)")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--n", type=int, default=10)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    settings = settings or get_settings()
    d3_path = settings.data_processed_dir / "d3_features.parquet"
    ledger_path = settings.data_processed_dir / "signal_ledger.jsonl"
    notes_path = settings.data_raw_dir / "d1_notes.jsonl"

    traces = trace_sample(d3_path, ledger_path, notes_path, extraction_run_id=args.run_id, n=args.n, seed=args.seed)
    complete = sum(t.is_complete for t in traces)
    print(f"Lineage sample: {len(traces)} feature rows traced, {complete} fully resolved.")
    for t in traces:
        print(f"\n{t.entity_key} @ {t.forecast_cutoff}: {len(t.signals)}/{len(t.contributing_signal_ids)} signals resolved")
        for s in t.signals:
            print(f"  signal={s.signal_id} source={s.source_id} span={s.evidence_span!r}")


if __name__ == "__main__":
    main()
