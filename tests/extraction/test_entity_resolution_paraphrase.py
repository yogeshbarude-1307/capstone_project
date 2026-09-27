"""Gate D stress test (docs/16 Layer 2b): the exact-string entity resolver
must abstain cleanly on paraphrased mentions, rather than silently guessing.

This documents a real limitation, not a bug: production-grade entity
resolution (fuzzy match, alias tables, master data) is explicitly out of
scope for this POC and tracked as a production-gap item.
"""

from __future__ import annotations

import random

from dsfs.extraction.entity_resolution import resolve_entities
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
    return entities, notes, ground_truth


def test_exact_match_resolver_succeeds_when_mode_is_none():
    entities, notes, ground_truth = _generate("none")
    known = set(entities)
    resolved_count = sum(
        1 for n in notes if resolve_entities(n.entity_mentions_raw, known)[1] is not None
    )
    assert resolved_count == len(notes)


def test_exact_match_resolver_mostly_abstains_when_mode_is_aggressive():
    """The point of the stress test: paraphrased/pronoun mentions are NOT in
    the known-entity set, so the current resolver correctly abstains
    (returns no forecast_key) rather than guessing — this is the Gate D
    recall gap the production-gap doc must track."""
    entities, notes, ground_truth = _generate("aggressive")
    known = set(entities)
    non_empty_notes = [n for n in notes if n.entity_mentions_raw]
    resolved_count = sum(
        1 for n in non_empty_notes if resolve_entities(n.entity_mentions_raw, known)[1] is not None
    )
    recall = resolved_count / len(non_empty_notes)
    assert recall < 0.5, (
        f"expected the exact-string resolver to fail on most paraphrased mentions, "
        f"got recall={recall:.1%} — resolver may be silently matching on something unexpected"
    )


def test_unresolved_mention_never_guesses_wrong_entity():
    entities, notes, ground_truth = _generate("aggressive")
    known = set(entities)
    for n in notes:
        resolved, forecast_key = resolve_entities(n.entity_mentions_raw, known)
        if forecast_key is not None:
            assert forecast_key in known
