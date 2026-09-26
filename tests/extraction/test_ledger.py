"""Ledger must be append-only: re-running extraction never overwrites prior
history (docs/07-extraction-pipeline-design.md versioning discipline)."""

from __future__ import annotations

from dsfs.extraction.extractor import extract_signal
from dsfs.extraction.ledger import append_to_ledger, read_ledger

from .conftest import make_evidence
import pytest


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


def test_identical_retry_is_idempotent_and_conflicting_id_is_rejected(tmp_path, known_entities):
    path = tmp_path / "ledger.jsonl"
    ev = make_evidence("EV-1", "Customer expects to increase orders.")
    sig = extract_signal(ev, known_entities, extraction_run_id="run-1")
    assert append_to_ledger([sig], path) == 1
    assert append_to_ledger([sig], path) == 0
    before = path.read_bytes()
    changed = sig.model_copy(update={"extractor_version": "changed"})
    with pytest.raises(ValueError, match="Conflicting content"):
        append_to_ledger([changed], path)
    assert path.read_bytes() == before


def test_source_edit_keeps_logical_identity_but_gets_a_new_physical_id(known_entities):
    ev = make_evidence("original", "Customer expects to increase orders.")
    edited = type(ev).model_validate({
        **ev.model_dump(), "source_id": "edited", "source_revision": "r2",
        "raw_text": "Customer expects to decrease orders.",
    })
    first = extract_signal(ev, known_entities, extraction_run_id="same-run")
    second = extract_signal(edited, known_entities, extraction_run_id="same-run")
    assert first.logical_signal_id == second.logical_signal_id
    assert first.signal_id != second.signal_id
