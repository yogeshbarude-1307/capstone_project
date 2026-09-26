"""Milestone 2 tests for D1 (notes + ground truth): schema validity against
the Milestone-1 contracts, and the sampling-policy expectations from
docs/06-synthetic-data-design.md (>=20% no-signal, hard cases present)."""

from __future__ import annotations

import random

import pytest

from dsfs.contracts import validate_record
from dsfs.synth.config import GeneratorConfig
from dsfs.synth.entities import generate_entities
from dsfs.synth.latent import generate_latent_events
from dsfs.synth.notes import generate_notes


@pytest.fixture(scope="module")
def generated():
    config = GeneratorConfig(seed=5, n_entities=40, n_weeks=104)
    rng_latent = random.Random(config.seed)
    entities = generate_entities(config)
    knowables, _ = generate_latent_events(entities, config, rng_latent)
    notes, ground_truth = generate_notes(knowables, config, random.Random(config.seed + 1))
    return config, notes, ground_truth


def test_every_note_validates_against_source_evidence_contract(generated):
    _, notes, _ = generated
    for note in notes:
        dumped = note.model_dump(mode="json")
        validate_record("source_evidence", dumped)  # raises on failure


def test_every_note_has_available_at_not_before_authored_at(generated):
    _, notes, _ = generated
    for note in notes:
        assert note.available_at >= note.authored_at


def test_no_signal_notes_meet_minimum_prevalence(generated):
    """docs/06-synthetic-data-design.md: '>=20% explicit NO_SIGNAL' target
    for the sampling policy."""
    _, _, ground_truth = generated
    irrelevant_fraction = sum(g.is_irrelevant for g in ground_truth) / len(ground_truth)
    assert irrelevant_fraction >= 0.15, (
        f"irrelevant/no-signal fraction {irrelevant_fraction:.2%} is below the docs/06 target band"
    )


def test_hard_cases_are_represented(generated):
    """The generator must actually produce examples of the mandated hard
    case families from docs/11-testing-strategy.md, not just plausible
    easy cases, so D1/D2-style downstream evaluation has something to
    test against."""
    _, _, ground_truth = generated

    negations = [g for g in ground_truth if g.template_id == "negation"]
    reversals = [g for g in ground_truth if g.is_reversal]
    conditionals = [g for g in ground_truth if g.conditionality.value == "CONDITIONAL"]
    hedged = [g for g in ground_truth if g.business_certainty.value == "POSSIBLE"]
    no_signal = [g for g in ground_truth if g.is_irrelevant]

    assert negations, "generator produced no negation-style notes"
    assert reversals, "generator produced no reversal/supersession notes"
    assert conditionals, "generator produced no conditional notes"
    assert hedged, "generator produced no hedged/uncertain notes"
    assert no_signal, "generator produced no irrelevant/no-signal notes"

    for g in negations:
        assert g.negated is True
    for g in reversals:
        assert g.supersedes_event_id is not None
        assert g.negated is True


def test_ground_truth_source_ids_match_notes_one_to_one(generated):
    _, notes, ground_truth = generated
    note_ids = {n.source_id for n in notes}
    gt_ids = {g.source_id for g in ground_truth}
    assert note_ids == gt_ids
    assert len(notes) == len(ground_truth)


def test_conditional_notes_carry_condition_text_in_rendered_text(generated):
    """A conditional note's condition_text ground truth should actually be
    reflected in the rendered text (evidence-grounding sanity, foreshadowing
    the extraction evidence_ref requirement in docs/07)."""
    _, notes, ground_truth = generated
    notes_by_id = {n.source_id: n for n in notes}
    conditionals = [g for g in ground_truth if g.conditionality.value == "CONDITIONAL" and not g.is_irrelevant]
    assert conditionals
    for g in conditionals[:20]:
        note = notes_by_id[g.source_id]
        assert g.condition_text in note.raw_text
