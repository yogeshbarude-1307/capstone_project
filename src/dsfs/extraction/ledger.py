"""Append-only local signal ledger.

Per docs/07's versioning discipline: a re-run of extraction must never
overwrite prior interpretations. append_to_ledger() always opens the ledger
file in append mode, never truncates it, and every record it writes already
carries its own extraction_run_id/extractor_version/schema_version so
history stays reconstructible even as the file accumulates rows across
multiple runs.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from dsfs.contracts import validate_record
from dsfs.models.common import as_utc
from dsfs.models.signal_record import RecordStatus, SignalRecord, ValidationStatus
from dsfs.models.source_evidence import SourceEvidence


def append_to_ledger(records: list[SignalRecord], ledger_path: Path) -> int:
    # Validate the entire batch before any append. A retried identical physical
    # record is idempotent; reusing its ID for different content is an error.
    existing = {row["signal_id"]: row for row in read_ledger(ledger_path)}
    pending = []
    for record in records:
        dumped = record.model_dump(mode="json")
        validate_record("signal_record", dumped)
        if record.signal_id in existing:
            if existing[record.signal_id] != dumped:
                raise ValueError(f"Conflicting content for signal_id {record.signal_id}")
            continue
        existing[record.signal_id] = dumped
        pending.append(dumped)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as f:
        for dumped in pending:
            f.write(json.dumps(dumped) + "\n")
    return len(pending)


def read_ledger(ledger_path: Path) -> list[dict]:
    if not ledger_path.exists():
        return []
    with ledger_path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def ledger_as_of(
    records: list[SignalRecord],
    sources: dict[str, SourceEvidence],
    cutoff: datetime,
    *,
    extraction_run_id: str,
) -> list[SignalRecord]:
    """Reconstruct source-knowledge-time state for one explicitly selected run.

    This is an offline historical replay, not a claim of live extraction at the
    cutoff. Feature horizon/validation filtering belongs to Milestone 5.
    Selecting a run prevents re-extractions from being counted as new events.
    """
    cutoff = as_utc(cutoff)
    visible = []
    for record in records:
        if record.extraction_run_id != extraction_run_id:
            continue
        source = sources[record.source_id]  # missing lineage fails rather than guessing
        if source.available_at <= cutoff:
            if source.source_revision != record.source_revision:
                raise ValueError("Source revision does not match ledger lineage")
            visible.append(record)
    superseded = {
        r.supersedes_signal_id for r in visible
        if r.validation_status == ValidationStatus.PASS and r.supersedes_signal_id
    }
    cancelled_refs = {r.business_event_ref for r in visible
                      if r.validation_status == ValidationStatus.PASS and r.supersedes_signal_id and r.business_event_ref}
    superseded.update(r.signal_id for r in visible if r.business_event_ref in cancelled_refs
                      and not r.supersedes_signal_id)
    return [r.model_copy(update={"record_status": RecordStatus.SUPERSEDED})
            if r.signal_id in superseded else r.model_copy(deep=True) for r in visible]
