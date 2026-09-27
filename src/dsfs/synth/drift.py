"""Seeded synthetic drift scenarios (docs/10, Milestone 10 D4).

Confined to text/metadata-level mutations applied during note rendering.
Deliberately does NOT touch latent.py/demand.py — those are the causal-
separation-critical modules covered by tests/synth/test_leakage.py, and
mutating them to shift direction-class proportions or the feature/demand
relationship (concept drift) would risk that invariant. Those two scenarios
from docs/10's list are left unimplemented; see docs/16-revised-execution-plan.md.
"""

from __future__ import annotations

import random
from datetime import date

from dsfs.models.source_evidence import SourceType

NOT_IMPLEMENTED = {
    "direction_class_shift": (
        "Direction is fixed by Knowable, produced in latent.py; shifting its "
        "class proportions post-injection would require date-conditional logic "
        "in the causal-separation-critical latent generator, not attempted here."
    ),
    "concept_drift": (
        "A deliberate change in the feature/demand relationship requires "
        "date-conditional logic in demand.py, the module test_leakage.py "
        "exists specifically to keep independent of note content; not attempted here."
    ),
}

_VOCAB_SUBSTITUTIONS = {
    "expects": "anticipates",
    "increase": "uptick",
    "decrease": "pull-back",
    "customer": "client",
    "orders": "bookings",
}

_ABBREVIATION_SUBSTITUTIONS = {
    "Customer": "Cust.",
    "customer": "cust.",
    "quarter": "Q",
    "approximately": "approx.",
    "management": "mgmt.",
}

_SHIFTED_SOURCE_TYPE_WEIGHTS = {
    SourceType.ACCOUNT_NOTE: 0.7,
    SourceType.SERVICE_NOTE: 0.1,
    SourceType.SUPPLIER_COMMENTARY: 0.1,
    SourceType.SALES_COMMENTARY: 0.1,
}


def is_past_injection(authored_at: date, config_start_date: date, inject_at_week: int) -> bool:
    week_index = (authored_at - config_start_date).days // 7
    return week_index >= inject_at_week


def apply_text_mutation(text: str, scenario: str) -> str:
    """Text-level scenarios: vocabulary_shift, new_abbreviations, note_length_shift."""
    if scenario == "vocabulary_shift":
        for old, new in _VOCAB_SUBSTITUTIONS.items():
            text = text.replace(old, new).replace(old.capitalize(), new.capitalize())
        return text
    if scenario == "new_abbreviations":
        for old, new in _ABBREVIATION_SUBSTITUTIONS.items():
            text = text.replace(old, new)
        return text
    if scenario == "note_length_shift":
        return text + " Additional context follows for completeness and audit purposes."
    return text


def choose_source_type(rng: random.Random, source_types: list[SourceType], scenario: str) -> SourceType:
    """source_type_mix_shift: skew the distribution instead of uniform choice."""
    if scenario != "source_type_mix_shift":
        return rng.choice(source_types)
    weights = [_SHIFTED_SOURCE_TYPE_WEIGHTS.get(t, 0.0) for t in source_types]
    return rng.choices(source_types, weights=weights, k=1)[0]


def effective_reversal_probability(base_probability: float, scenario: str) -> float:
    """contradiction_rate_increase: reversals become up to 3x more likely."""
    if scenario == "contradiction_rate_increase":
        return min(1.0, base_probability * 3.0)
    return base_probability
