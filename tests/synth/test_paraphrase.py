"""Entity-paraphrase stress test infrastructure (docs/16 Layer 2b).

Default mode="none" must be unchanged (byte-for-byte reproducibility of
existing fixtures). "mild"/"aggressive" must produce mentions that diverge
from the canonical entity_key, deterministically given the seed, while
NoteGroundTruth.entity_key always carries the true linkage regardless of mode.
"""

from __future__ import annotations

import random

from dsfs.synth.config import GeneratorConfig
from dsfs.synth.entities import generate_entities
from dsfs.synth.latent import generate_latent_events
from dsfs.synth.notes import generate_notes


def _generate(mode: str, seed: int = 5):
    config = GeneratorConfig(seed=seed, n_entities=10, n_weeks=52, entity_paraphrase_mode=mode)
    rng_latent = random.Random(config.seed)
    entities = generate_entities(config)
    knowables, _ = generate_latent_events(entities, config, rng_latent)
    notes, ground_truth = generate_notes(knowables, config, random.Random(config.seed + 1))
    return notes, ground_truth


def test_none_mode_renders_canonical_entity_key_verbatim():
    notes, ground_truth = _generate("none")
    gt_by_source = {g.source_id: g for g in ground_truth}
    for note in notes:
        gt = gt_by_source[note.source_id]
        if gt.entity_key is not None:
            assert note.entity_mentions_raw == [gt.entity_key]


def test_mild_mode_never_renders_canonical_entity_key():
    notes, ground_truth = _generate("mild")
    gt_by_source = {g.source_id: g for g in ground_truth}
    diverged = 0
    for note in notes:
        gt = gt_by_source[note.source_id]
        if gt.entity_key is not None:
            assert note.entity_mentions_raw != [gt.entity_key]
            diverged += 1
    assert diverged > 0


def test_aggressive_mode_produces_pronouns_and_hierarchy_refs():
    notes, ground_truth = _generate("aggressive")
    mentions = {tuple(n.entity_mentions_raw) for n in notes if n.entity_mentions_raw}
    assert ("they",) in mentions or ("the customer",) in mentions or ("the account",) in mentions


def test_ground_truth_entity_key_always_correct_regardless_of_mode():
    """The paraphrase must never corrupt the generator's own linkage — only
    the rendered mention text changes."""
    _, gt_none = _generate("none", seed=7)
    _, gt_aggressive = _generate("aggressive", seed=7)
    entity_keys_none = [g.entity_key for g in gt_none if not g.is_irrelevant]
    entity_keys_aggressive = [g.entity_key for g in gt_aggressive if not g.is_irrelevant]
    assert entity_keys_none == entity_keys_aggressive


def test_paraphrase_is_deterministic_given_seed():
    notes_a, _ = _generate("aggressive", seed=11)
    notes_b, _ = _generate("aggressive", seed=11)
    mentions_a = [n.entity_mentions_raw for n in notes_a]
    mentions_b = [n.entity_mentions_raw for n in notes_b]
    assert mentions_a == mentions_b
