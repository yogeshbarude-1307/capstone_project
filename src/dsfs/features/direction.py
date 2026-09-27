"""Shared direction-vote arithmetic used by both feature transformation and oracle features."""

from __future__ import annotations


def direction_vote(direction: str, negated: bool) -> int:
    """Return +1 for increase, -1 for decrease, 0 for neutral/unknown.

    Accepts any string-valued direction (``Direction`` is a ``StrEnum``, and the
    generator's ground-truth records carry plain strings).
    """
    if direction == "INCREASE":
        return -1 if negated else 1
    if direction == "DECREASE":
        return 1 if negated else -1
    return 0
