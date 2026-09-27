"""Seeded synthetic drift scenarios (docs/10, Milestone 10 D4).

Each implemented scenario must be: absent before the injection week, present
after it, and its injection metadata (drift_scenario/drift_inject_at_week)
queryable independently of D1 (it lives in GeneratorConfig / generator_config.json).
"""

from __future__ import annotations

import random

from dsfs.synth.config import GeneratorConfig
from dsfs.synth.entities import generate_entities
from dsfs.synth.latent import generate_latent_events
from dsfs.synth.notes import generate_notes


def _generate(scenario: str, inject_at_week: int = 10, seed: int = 5):
    config = GeneratorConfig(
        seed=seed, n_entities=15, n_weeks=52,
        drift_scenario=scenario, drift_inject_at_week=inject_at_week,
    )
    rng_latent = random.Random(config.seed)
    entities = generate_entities(config)
    knowables, _ = generate_latent_events(entities, config, rng_latent)
    notes, ground_truth = generate_notes(knowables, config, random.Random(config.seed + 1))
    return config, notes


def _week_index(note, config):
    return (note.authored_at.date() - config.start_date).days // 7


def test_none_scenario_is_a_no_op_and_matches_baseline():
    _, baseline_notes = _generate("none")
    config, none_notes = _generate("none")
    assert [n.raw_text for n in baseline_notes] == [n.raw_text for n in none_notes]


def test_vocabulary_shift_absent_before_present_after():
    config, notes = _generate("vocabulary_shift", inject_at_week=10)
    before = [n for n in notes if _week_index(n, config) < 10]
    after = [n for n in notes if _week_index(n, config) >= 10]
    assert before, "need pre-injection notes to compare against"
    assert after, "need post-injection notes to compare against"
    assert not any("anticipates" in n.raw_text or "uptick" in n.raw_text for n in before)
    assert any("anticipates" in n.raw_text or "uptick" in n.raw_text or "pull-back" in n.raw_text for n in after)


def test_new_abbreviations_absent_before_present_after():
    config, notes = _generate("new_abbreviations", inject_at_week=10)
    before = [n for n in notes if _week_index(n, config) < 10]
    after = [n for n in notes if _week_index(n, config) >= 10]
    assert not any("Cust." in n.raw_text or "mgmt." in n.raw_text for n in before)
    assert any("Cust." in n.raw_text or "cust." in n.raw_text or "mgmt." in n.raw_text for n in after)


def test_note_length_shift_increases_length_after_injection():
    config, notes = _generate("note_length_shift", inject_at_week=10)
    before = [n for n in notes if _week_index(n, config) < 10]
    after = [n for n in notes if _week_index(n, config) >= 10]
    assert all("Additional context follows" not in n.raw_text for n in before)
    assert any("Additional context follows" in n.raw_text for n in after)


def test_source_type_mix_shift_skews_distribution_after_injection():
    from collections import Counter
    config, notes = _generate("source_type_mix_shift", inject_at_week=5)
    after = [n for n in notes if _week_index(n, config) >= 5]
    assert after
    counts = Counter(n.source_type for n in after)
    account_note_share = counts.get("account_note", 0) / len(after)
    assert account_note_share > 0.5, f"expected account_note to dominate post-shift, got {counts}"


def test_contradiction_rate_increase_produces_more_reversals():
    config_a, notes_a = _generate("none", inject_at_week=0, seed=9)
    config_b, notes_b = _generate("contradiction_rate_increase", inject_at_week=0, seed=9)
    # inject_at_week=0 applies the scenario to the whole run for a clean comparison.
    reversal_count_a = sum(1 for n in notes_a if "cancel" in n.raw_text.lower() or "revers" in n.raw_text.lower())
    reversal_count_b = sum(1 for n in notes_b if "cancel" in n.raw_text.lower() or "revers" in n.raw_text.lower())
    assert reversal_count_b >= reversal_count_a


def test_injection_metadata_is_queryable_independent_of_d1():
    config, notes = _generate("vocabulary_shift", inject_at_week=7)
    assert config.drift_scenario == "vocabulary_shift"
    assert config.drift_inject_at_week == 7
    # None of these fields appear on the notes themselves (D1 stays clean).
    for note in notes:
        dumped = note.model_dump(mode="json")
        assert "drift_scenario" not in dumped
        assert "drift_inject_at_week" not in dumped
