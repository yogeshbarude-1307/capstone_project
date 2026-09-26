"""Note-text templates and phrasing helpers.

Renders text from a Knowable ONLY (see latent.py / notes.py). Templates are
deliberately designed to cover the five mandated hard cases from
docs/11-testing-strategy.md: negation, conditionality, future-dated
expectation, reversal/supersession, and hedged uncertainty.
"""

from __future__ import annotations

import random
from datetime import datetime

from dsfs.models.signal_record import BusinessCertainty, Conditionality, Direction, SignalType


def time_phrase(authored_at: datetime, effective_start: datetime) -> str:
    days_ahead = (effective_start - authored_at).days
    if days_ahead <= 10:
        return "in the next couple of weeks"
    if days_ahead <= 35:
        return "next month"
    if days_ahead <= 100:
        return "next quarter"
    if days_ahead <= 200:
        return "later this year"
    return "next year"


_CERTAINTY_PHRASE = {
    BusinessCertainty.ASSERTED: "confirmed they will",
    BusinessCertainty.EXPECTED: "expects to",
    BusinessCertainty.LIKELY: "will likely",
    BusinessCertainty.POSSIBLE: "indicated they might",
    BusinessCertainty.UNKNOWN: "mentioned they may possibly",
}

_DIRECTION_VERB = {
    Direction.INCREASE: "increase",
    Direction.DECREASE: "decrease",
}

_SUBTYPE_NOUN = {
    SignalType.DEMAND_EXPECTATION: "orders",
    SignalType.PURCHASE_INTENT: "purchase volume",
    SignalType.ORDER_LIFECYCLE: "the order",
    SignalType.QUANTITY_REVISION: "the order quantity",
    SignalType.TIMING_REVISION: "the delivery schedule",
    SignalType.INVENTORY_POSITION: "inventory",
    SignalType.COMMERCIAL_EVENT: "volume tied to the upcoming promotion",
    SignalType.SUPPLY_FULFILLMENT: "our ability to fulfill on time",
    SignalType.MARKET_CONTEXT: "market demand",
}


def _magnitude_phrase(stated_value: float | None, stated_unit: str | None) -> str:
    if stated_value is None:
        return ""
    return f" by roughly {stated_value:g}{'%' if stated_unit == '%' else f' {stated_unit}'}"


def _condition_clause(condition_text: str | None) -> str:
    return f" {condition_text}" if condition_text else ""


def render_standard_note(
    *,
    signal_type: SignalType,
    direction: Direction,
    business_certainty: BusinessCertainty,
    conditionality: Conditionality,
    condition_text: str | None,
    stated_magnitude_value: float | None,
    stated_magnitude_unit: str | None,
    authored_at: datetime,
    effective_start: datetime,
    rng: random.Random,
) -> str:
    """The general-case renderer, covering hard cases 2 (conditional) and 3
    (future-dated expectation) directly, and feeding hedge phrasing for
    hard case 5 through the certainty-verb map."""
    noun = _SUBTYPE_NOUN.get(signal_type, "demand")
    certainty_phrase = _CERTAINTY_PHRASE[business_certainty]
    magnitude = _magnitude_phrase(stated_magnitude_value, stated_magnitude_unit)
    when = time_phrase(authored_at, effective_start)
    condition = _condition_clause(condition_text) if conditionality == Conditionality.CONDITIONAL else ""

    if direction == Direction.STABLE:
        action = f"keep {noun} steady"
    else:
        verb = _DIRECTION_VERB.get(direction, "change")
        action = f"{verb} {noun}{magnitude}"

    templates = [
        f"Customer {certainty_phrase} {action} {when}{condition}.",
        f"Account contact reports that the customer {certainty_phrase} {action} {when}{condition}.",
        f"Note from account review: customer {certainty_phrase} {action} {when}{condition}.",
    ]
    return rng.choice(templates)


def render_negation_note(
    *, signal_type: SignalType, authored_at: datetime, effective_start: datetime, rng: random.Random
) -> str:
    """Hard case 1: negation. The note explicitly denies an increase; ground
    truth for this note is direction=STABLE, negated=True — a naive
    extractor that pattern-matches on 'increasing' alone would wrongly
    emit direction=INCREASE here."""
    noun = _SUBTYPE_NOUN.get(signal_type, "the order")
    templates = [
        f"Customer is not increasing {noun}.",
        f"Customer confirmed there is no increase planned for {noun}.",
        f"Despite earlier speculation, {noun} will not be going up.",
    ]
    return rng.choice(templates)


def render_reversal_note(
    *, original_signal_type: SignalType, authored_at: datetime, rng: random.Random
) -> str:
    """Hard case 4: reversal/supersession. References an earlier plan being
    cancelled; ground truth supersedes_event_id points back to the original
    event."""
    noun = _SUBTYPE_NOUN.get(original_signal_type, "the plan")
    templates = [
        f"Previous expansion plan for {noun} has been cancelled.",
        f"Update: the earlier change to {noun} is no longer happening.",
        f"Customer reversed their previous decision regarding {noun}.",
    ]
    return rng.choice(templates)


_IRRELEVANT_TEMPLATES = [
    "Updated primary contact email on file for the account.",
    "Scheduled quarterly business review for next Tuesday.",
    "Resolved a billing discrepancy from last invoice cycle.",
    "Customer asked a general question about the support portal.",
    "Logged a routine check-in call; no new information to report.",
    "Shipping address updated per customer request.",
]


def render_irrelevant_note(rng: random.Random) -> str:
    return rng.choice(_IRRELEVANT_TEMPLATES)
