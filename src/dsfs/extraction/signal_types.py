"""Independent noun-phrase -> signal_type lookup table for the rules stage.

Written independently from dsfs.synth.templates (never imported from it) —
the extraction pipeline must be built the way a real NLP developer would
build it, from reading example notes and writing matching patterns, not by
importing the generator's private rendering internals. That the vocabulary
overlaps with the synthetic templates is expected (they describe the same
domain); the coupling that matters is that this module has no import
dependency on dsfs.synth at all.
"""

from __future__ import annotations

import re

from dsfs.models.signal_record import SignalType

# Longest, most specific phrases first so a substring match can't accidentally
# hit a shorter, less specific phrase contained within a longer one.
_SIGNAL_TYPE_NOUN_PHRASES: list[tuple[str, SignalType]] = [
    ("volume tied to the upcoming promotion", SignalType.COMMERCIAL_EVENT),
    ("our ability to fulfill on time", SignalType.SUPPLY_FULFILLMENT),
    ("the order quantity", SignalType.QUANTITY_REVISION),
    ("the delivery schedule", SignalType.TIMING_REVISION),
    ("purchase volume", SignalType.PURCHASE_INTENT),
    ("market demand", SignalType.MARKET_CONTEXT),
    ("inventory", SignalType.INVENTORY_POSITION),
    ("the order", SignalType.ORDER_LIFECYCLE),
    ("orders", SignalType.DEMAND_EXPECTATION),
    # Generic fallbacks (deliberately last / shortest, so a more specific
    # phrase above always wins a substring match first): a note that talks
    # about "volume" or "demand" without naming a more specific subject is
    # still evidence of a DEMAND_EXPECTATION-class signal, just a vaguer one.
    ("volume", SignalType.DEMAND_EXPECTATION),
    ("demand", SignalType.DEMAND_EXPECTATION),
]
_SIGNAL_TYPE_NOUN_PHRASES.sort(key=lambda pair: -len(pair[0]))


def detect_signal_type(text: str) -> SignalType | None:
    lower = text.lower()
    for phrase, signal_type in _SIGNAL_TYPE_NOUN_PHRASES:
        if re.search(re.escape(phrase), lower):
            return signal_type
    return None
