"""Milestone 3 acceptance test (docs/12): ">=99.5% schema-conformant output;
invalid records are quarantined, never silently accepted." Run over the full
Milestone 2 synthetic corpus, not a hand-picked sample."""

from __future__ import annotations

import random

import pytest

from dsfs.contracts import validate_record
from dsfs.extraction.pipeline import run_extraction
from dsfs.synth.config import GeneratorConfig
from dsfs.synth.entities import generate_entities
from dsfs.synth.latent import generate_latent_events
from dsfs.synth.notes import generate_notes

MIN_SCHEMA_CONFORMANCE_RATE = 0.995  # docs/00 Q1 / docs/12 Milestone 3 provisional gate


@pytest.fixture(scope="module")
def full_corpus_notes():
    config = GeneratorConfig(seed=9, n_entities=40, n_weeks=104)
    entities = generate_entities(config)
    rng_latent = random.Random(config.seed)
    knowables, _ = generate_latent_events(entities, config, rng_latent)
    notes, _ = generate_notes(knowables, config, random.Random(config.seed + 1))
    return entities, notes


def test_schema_conformance_rate_meets_gate(full_corpus_notes):
    entities, notes = full_corpus_notes
    result = run_extraction(notes, set(entities))

    assert len(notes) > 100, "test corpus too small to be a meaningful conformance sample"
    assert result.schema_conformance_rate >= MIN_SCHEMA_CONFORMANCE_RATE, (
        f"schema_conformance_rate={result.schema_conformance_rate:.4f} below the "
        f"{MIN_SCHEMA_CONFORMANCE_RATE:.3f} provisional gate; quarantined="
        f"{[(q.source_id, q.stage, q.error) for q in result.quarantined][:5]}"
    )


def test_every_accepted_record_independently_revalidates_against_the_contract(full_corpus_notes):
    """Belt-and-braces: re-validate the accepted output a second time,
    independent of the pipeline's own internal check."""
    entities, notes = full_corpus_notes
    result = run_extraction(notes, set(entities))
    for record in result.accepted:
        validate_record("signal_record", record.model_dump(mode="json"))  # raises on failure


def test_quarantined_records_carry_diagnostic_information(full_corpus_notes):
    entities, notes = full_corpus_notes
    result = run_extraction(notes, set(entities))
    for q in result.quarantined:
        assert q.source_id
        assert q.error
        assert q.stage in ("construct", "contract")


def test_every_note_produces_exactly_one_signal_or_one_quarantine_entry(full_corpus_notes):
    entities, notes = full_corpus_notes
    result = run_extraction(notes, set(entities))
    assert len(result.accepted) + len(result.quarantined) == len(notes)


def test_no_signal_notes_correctly_abstain_rather_than_fabricate(full_corpus_notes):
    from dsfs.models.signal_record import Direction, SignalType

    entities, notes = full_corpus_notes
    result = run_extraction(notes, set(entities))
    no_signal_records = [r for r in result.accepted if r.signal_type == SignalType.NO_SIGNAL]
    assert no_signal_records, "expected some NO_SIGNAL abstentions in a corpus with ~20% irrelevant notes"
    for r in no_signal_records:
        assert r.direction == Direction.NA
        assert r.magnitude_value is None
        assert r.abstention_reason is not None


def test_quarantine_is_persisted_with_source_and_run(tmp_path, monkeypatch, known_entities):
    import json
    from dsfs.extraction import pipeline
    from dsfs.extraction.extractor import extract_signal
    from .conftest import make_evidence

    evidence = make_evidence("bad", "Customer expects to increase orders.")
    def malformed(*args, **kwargs):
        # Bypass Pydantic deliberately to exercise the independent wire-contract gate.
        return extract_signal(*args, **kwargs).model_copy(update={"schema_version": "invalid"})
    monkeypatch.setattr(pipeline, "extract_signal", malformed)
    result = pipeline.run_and_persist([evidence], known_entities, tmp_path / "ledger.jsonl", extraction_run_id="reject-run")
    assert not result.accepted
    assert len(result.quarantined) == 1
    row = json.loads((tmp_path / "ledger_rejected.jsonl").read_text())
    assert row["source_evidence"]["raw_text"] == evidence.raw_text
    assert row["extraction_run_id"] == "reject-run"
    assert row["rejected_record"]["schema_version"] == "invalid"
    assert row["error"]


def test_unresolved_entity_requires_review(known_entities):
    from dsfs.models import ValidationStatus
    from .conftest import make_evidence
    note = make_evidence("unknown", "Customer expects to increase orders.", entity_mentions=["missing"])
    signal = run_extraction([note], known_entities).accepted[0]
    assert signal.forecast_key is None
    assert signal.validation_status == ValidationStatus.REVIEW


def test_cli_refuses_enabled_unimplemented_llm_before_writing(tmp_path):
    from dsfs.config import Settings
    from dsfs.extraction.pipeline import main
    target = tmp_path / "should-not-exist"
    with pytest.raises(NotImplementedError, match="Local LLM"):
        main(Settings(llm_extraction_enabled=True, data_raw_dir=target))
    assert not target.exists()
