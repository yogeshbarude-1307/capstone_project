"""Reversals must not rewrite history, guess a target, or see future evidence."""

from datetime import datetime, timezone

from dsfs.extraction.ledger import ledger_as_of
from dsfs.extraction.pipeline import run_extraction
from dsfs.models import RecordStatus, ValidationStatus

from .conftest import make_evidence


def _reversal():
    return make_evidence(
        "cancel", "Previous expansion plan has been cancelled.",
        authored_at="2026-01-07T09:00:00Z", available_at="2026-01-07T10:00:00Z",
    )


def test_reversal_supersedes_unique_prior_only_after_it_becomes_available(known_entities):
    original = make_evidence("original", "Customer expects to increase orders next month.")
    cancellation = _reversal()
    notes = [cancellation, original]  # input order must not influence knowledge-time order
    result = run_extraction(notes, known_entities, extraction_run_id="run-test")
    prior, reversal = result.accepted
    assert reversal.supersedes_signal_id == prior.signal_id
    assert reversal.related_signal_ids == [prior.signal_id]
    assert reversal.validation_status == ValidationStatus.PASS
    sources = {n.source_id: n for n in notes}
    before = ledger_as_of(result.accepted, sources, datetime(2026, 1, 7, 9, 30), extraction_run_id="run-test")
    assert len(before) == 1
    assert before[0].record_status == RecordStatus.ACTIVE
    after = ledger_as_of(result.accepted, sources, datetime(2026, 1, 7, 10), extraction_run_id="run-test")
    assert after[0].record_status == RecordStatus.SUPERSEDED
    assert after[1].record_status == RecordStatus.ACTIVE
    assert prior.record_status == RecordStatus.ACTIVE  # immutable physical history


def test_ambiguous_reversal_stays_review(known_entities):
    notes = [
        make_evidence("one", "Customer expects to increase orders next month."),
        make_evidence("two", "Customer expects to increase purchase volume next month."),
        _reversal(),
    ]
    reversal = run_extraction(notes, known_entities).accepted[-1]
    assert reversal.validation_status == ValidationStatus.REVIEW
    assert reversal.supersedes_signal_id is None


def test_reversal_cannot_link_to_a_claim_unavailable_when_it_was_authored(known_entities):
    prior = make_evidence(
        "late", "Customer expects to increase orders next month.",
        available_at="2026-01-07T09:30:00Z",
    )
    reversal = run_extraction([prior, _reversal()], known_entities).accepted[-1]
    assert reversal.validation_status == ValidationStatus.REVIEW
    assert reversal.supersedes_signal_id is None


def test_replay_is_reproducible_and_ledger_view_selects_one_run(known_entities):
    notes = [make_evidence("one", "Customer expects to increase orders next month."), _reversal()]
    clock = datetime(2026, 2, 1, tzinfo=timezone.utc)
    first = run_extraction(notes, known_entities, extraction_run_id="r1", extracted_at=clock)
    repeat = run_extraction(list(reversed(notes)), known_entities, extraction_run_id="r1", extracted_at=clock)
    assert first == repeat
    other = run_extraction(notes, known_entities, extraction_run_id="r2", extracted_at=clock)
    assert first.accepted[0].signal_id != other.accepted[0].signal_id
    assert first.accepted[0].logical_signal_id == other.accepted[0].logical_signal_id
    view = ledger_as_of(first.accepted + other.accepted, {n.source_id: n for n in notes}, clock, extraction_run_id="r2")
    assert len(view) == 2
    assert all(r.extraction_run_id == "r2" for r in view)
