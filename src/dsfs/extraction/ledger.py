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
from pathlib import Path

from dsfs.models.signal_record import SignalRecord


def append_to_ledger(records: list[SignalRecord], ledger_path: Path) -> int:
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record.model_dump(mode="json")) + "\n")
    return len(records)


def read_ledger(ledger_path: Path) -> list[dict]:
    if not ledger_path.exists():
        return []
    with ledger_path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]
