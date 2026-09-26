"""Milestone 3 acceptance test (docs/12): "all five hard cases produce the
documented expected interpretation," exact sentences and expectations from
docs/11-testing-strategy.md."""

from __future__ import annotations

from dsfs.extraction.extractor import extract_signal
from dsfs.models.signal_record import (
    BusinessCertainty,
    Conditionality,
    Direction,
    SignalType,
    ValidationStatus,
)

from .conftest import make_evidence


class TestHardCase1Negation:
    """'Customer is not increasing the order.' must NOT become
    direction=INCREASE; correct extraction recognizes the negated
    proposition."""

    def test_negation_is_recognized_and_direction_is_not_a_false_increase(self, known_entities):
        ev = make_evidence("EV-1", "Customer is not increasing the order.")
        sig = extract_signal(ev, known_entities, extraction_run_id="run-test")

        assert sig.negated is True
        assert sig.direction != Direction.INCREASE
        assert sig.direction in (Direction.STABLE, Direction.NA)
        assert sig.validation_status == ValidationStatus.PASS


class TestHardCase2Conditional:
    """'Customer may increase volume if the promotion is approved.' ->
    direction=INCREASE, business_certainty=POSSIBLE, conditionality=
    CONDITIONAL, condition_text='if the promotion is approved'."""

    def test_conditional_note_extracts_full_expected_structure(self, known_entities):
        ev = make_evidence(
            "EV-2", "Customer may increase volume if the promotion is approved."
        )
        sig = extract_signal(ev, known_entities, extraction_run_id="run-test")

        assert sig.signal_type == SignalType.DEMAND_EXPECTATION
        assert sig.direction == Direction.INCREASE
        assert sig.business_certainty == BusinessCertainty.POSSIBLE
        assert sig.conditionality == Conditionality.CONDITIONAL
        assert sig.condition_text == "if the promotion is approved"
        assert sig.negated is False


class TestHardCase3FutureEvent:
    """'Expected to increase orders next month.' -> direction=INCREASE,
    business_certainty=EXPECTED, effective_start/end normalized relative to
    authored_at, never the current wall clock."""

    def test_future_event_time_is_normalized_relative_to_authored_at(self, known_entities):
        ev = make_evidence(
            "EV-3", "Expected to increase orders next month.", authored_at="2026-01-05T09:00:00"
        )
        sig = extract_signal(ev, known_entities, extraction_run_id="run-test")

        assert sig.signal_type == SignalType.DEMAND_EXPECTATION
        assert sig.direction == Direction.INCREASE
        assert sig.business_certainty == BusinessCertainty.EXPECTED
        assert sig.time_expression_raw == "next month"
        assert sig.effective_start is not None
        # Must be computed relative to authored_at (Jan 2026), not "today".
        assert sig.effective_start.year == 2026
        assert sig.effective_start.month in (1, 2)
        assert sig.effective_start > ev.authored_at

    def test_different_authored_at_shifts_the_same_time_phrase(self, known_entities):
        """Proves the normalization is relative, not a hardcoded date."""
        ev_early = make_evidence(
            "EV-3a",
            "Expected to increase orders next month.",
            authored_at="2020-06-01T00:00:00",
            available_at="2020-06-01T00:10:00",
        )
        ev_late = make_evidence(
            "EV-3b",
            "Expected to increase orders next month.",
            authored_at="2030-06-01T00:00:00",
            available_at="2030-06-01T00:10:00",
        )
        sig_early = extract_signal(ev_early, known_entities, extraction_run_id="run-test")
        sig_late = extract_signal(ev_late, known_entities, extraction_run_id="run-test")
        assert sig_early.effective_start.year == 2020
        assert sig_late.effective_start.year == 2030


class TestHardCase4ReversalSupersession:
    """'Previous expansion plan has been cancelled.' The extractor must NOT
    silently confirm an increase (i.e. must not remain confidently
    ACTIVE/INCREASE about the original claim). Cross-signal
    supersedes_signal_id linking against a prior ledger entry is a
    reconciliation step owned by a later pipeline stage (docs/03-data-
    model.md 'Duplicate/conflict engine'; Business Problem doc 'Duplicate,
    conflicting, and evolving signals'), not the single-note extractor —
    that is out of Milestone 3 scope by design and is exercised again once
    the reconciliation stage exists."""

    def test_cancellation_is_recognized_as_negated_and_not_a_false_increase(self, known_entities):
        ev = make_evidence("EV-4", "Previous expansion plan has been cancelled.")
        sig = extract_signal(ev, known_entities, extraction_run_id="run-test")

        assert sig.negated is True
        assert sig.direction != Direction.INCREASE
        # Honest abstention (REVIEW) is the correct behavior here: the note
        # does not name a specific subject/signal_type, so the extractor
        # must not guess one (docs/07: never fabricate unsupported values).
        assert sig.validation_status == ValidationStatus.REVIEW
        assert sig.abstention_reason is not None


class TestHardCase5Uncertainty:
    """'Customer indicated they might need additional inventory.' ->
    business_certainty=POSSIBLE (hedged), not ASSERTED."""

    def test_hedged_uncertainty_is_not_treated_as_asserted_fact(self, known_entities):
        ev = make_evidence(
            "EV-5", "Customer indicated they might need additional inventory."
        )
        sig = extract_signal(ev, known_entities, extraction_run_id="run-test")

        assert sig.business_certainty == BusinessCertainty.POSSIBLE
        assert sig.business_certainty != BusinessCertainty.ASSERTED
        assert sig.signal_type in (SignalType.INVENTORY_POSITION, SignalType.PURCHASE_INTENT)
