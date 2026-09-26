"""Ledger must be append-only: re-running extraction never overwrites prior
history (docs/07-extraction-pipeline-design.md versioning discipline)."""

from __future__ import annotations

from dsfs.extraction.extractor import extract_signal
from dsfs.extraction.ledger import append_to_ledger, read_ledger

from .conftest import make_evidence


def test_append_writes_new_file_when_absent(tmp_path, known_entities):
    ledger_path = tmp_path / "signal_ledger.jsonl"
    ev = make_evidence("EV-1", "Customer confirmed they will increase orders by roughly 10%.")
    sig = extract_signal(ev, known_entities, extraction_run_id="run-1")

    n_written = append_to_ledger([sig], ledger_path)
    assert n_written == 1
    assert ledger_path.exists()
    assert len(read_ledger(ledger_path)) == 1


def test_second_run_appends_without_erasing_first_run(tmp_path, known_entities):
    ledger_path = tmp_path / "signal_ledger.jsonl"
    ev1 = make_evidence("EV-1", "Customer confirmed they will increase orders by roughly 10%.")
    ev2 = make_evidence("EV-2", "Customer confirmed they will decrease orders by roughly 5%.")

    sig1 = extract_signal(ev1, known_entities, extraction_run_id="run-1")
    append_to_ledger([sig1], ledger_path)

    sig2 = extract_signal(ev2, known_entities, extraction_run_id="run-2")
    append_to_ledger([sig2], ledger_path)

    rows = read_ledger(ledger_path)
    assert len(rows) == 2
    run_ids = {row["extraction_run_id"] for row in rows}
    assert run_ids == {"run-1", "run-2"}
    source_ids = {row["source_id"] for row in rows}
    assert source_ids == {"EV-1", "EV-2"}


def test_read_ledger_on_missing_file_returns_empty_list(tmp_path):
    assert read_ledger(tmp_path / "does_not_exist.jsonl") == []
