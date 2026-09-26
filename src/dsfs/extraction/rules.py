"""Deterministic rule-based cue detection: direction, negation, certainty,
conditionality, magnitude, and effective-time window.

This is the "rules" half of the hybrid pipeline (docs/07). It is also, for
now, the *entire* semantic-extraction stage: with the local LLM stage
disabled by default (docs/14-open-questions.md item 1), this module and
signal_types.py together ARE the documented degradation path, not a
placeholder for it.

Every function here returns None / UNKNOWN rather than guessing when a cue
is absent -- see docs/07-extraction-pipeline-design.md, "never fabricate
unsupported values."
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from dsfs.models.signal_record import BusinessCertainty, Conditionality, Direction, MagnitudeBasis

_INCREASE_IMPLYING_PATTERNS = [
    r"\bneeds?\s+additional\b",
    r"\bneeds?\s+more\b",
]


_NEGATION_PATTERNS = [
    r"\bis not increasing\b",
    r"\bno increase planned\b",
    r"\bwill not be going up\b",
    r"\breversed their previous decision\b",
    r"\bcancelled\b",
    r"\bno longer happening\b",
]


def detect_direction_and_negation(text: str) -> tuple[Direction | None, bool, bool]:
    """Returns (direction, negated, conflict).

    conflict=True means both increase and decrease cues were found in the
    same note -- a real signal of ambiguity, not something to silently
    resolve one way or the other (see docs/07 error taxonomy: "wrong
    direction" is a scored failure mode, so an honest MIXED/REVIEW is
    preferred over a coin-flip guess).
    """
    lower = text.lower()

    if any(re.search(p, lower) for p in _NEGATION_PATTERNS):
        return Direction.STABLE, True, False

    has_steady = bool(re.search(r"\bkeep\b.*\bsteady\b", lower))
    has_increase = bool(re.search(r"\bincrease\b", lower)) and "no increase" not in lower
    has_increase = has_increase or any(re.search(p, lower) for p in _INCREASE_IMPLYING_PATTERNS)
    has_decrease = bool(re.search(r"\bdecrease\b", lower))

    if has_increase and has_decrease:
        return Direction.MIXED, False, True
    if has_steady:
        return Direction.STABLE, False, False
    if has_increase:
        return Direction.INCREASE, False, False
    if has_decrease:
        return Direction.DECREASE, False, False
    return None, False, False


_CERTAINTY_PHRASE_PRIORITY: list[tuple[str, BusinessCertainty]] = [
    ("confirmed they will", BusinessCertainty.ASSERTED),
    ("mentioned they may possibly", BusinessCertainty.UNKNOWN),
    ("indicated they might", BusinessCertainty.POSSIBLE),
    ("will likely", BusinessCertainty.LIKELY),
    ("expects to", BusinessCertainty.EXPECTED),
    ("expected to", BusinessCertainty.EXPECTED),
]

_CERTAINTY_KEYWORD_FALLBACK: list[tuple[str, BusinessCertainty]] = [
    ("might", BusinessCertainty.POSSIBLE),
    ("may", BusinessCertainty.POSSIBLE),
    ("confirmed", BusinessCertainty.ASSERTED),
    ("expect", BusinessCertainty.EXPECTED),
    ("will", BusinessCertainty.LIKELY),
]


def detect_certainty(text: str) -> BusinessCertainty:
    lower = text.lower()
    for phrase, certainty in _CERTAINTY_PHRASE_PRIORITY:
        if phrase in lower:
            return certainty
    for keyword, certainty in _CERTAINTY_KEYWORD_FALLBACK:
        if re.search(r"\b" + re.escape(keyword) + r"\b", lower):
            return certainty
    return BusinessCertainty.UNKNOWN


_CONDITION_PATTERN = re.compile(r"\b(if [^.]+|pending [^.]+|unless [^.]+)", re.IGNORECASE)


def detect_conditionality(text: str) -> tuple[Conditionality, str | None]:
    match = _CONDITION_PATTERN.search(text)
    if not match:
        return Conditionality.NONE, None
    return Conditionality.CONDITIONAL, match.group(1).strip().rstrip(".")


_MAGNITUDE_PATTERN = re.compile(r"roughly\s+(\d+(?:\.\d+)?)\s*%", re.IGNORECASE)


def detect_magnitude(text: str) -> tuple[float | None, str | None, MagnitudeBasis | None]:
    match = _MAGNITUDE_PATTERN.search(text)
    if not match:
        return None, None, None
    return float(match.group(1)), "%", MagnitudeBasis.PERCENT


def is_reversal(text: str) -> bool:
    """Only explicit reversal language; ordinary negation is not a reversal."""
    return bool(re.search(
        r"\bcancelled\b|\bcanceled\b|\bno longer happening\b|\breversed their previous decision\b",
        text, re.IGNORECASE,
    ))


def _month_start(authored_at: datetime, month_offset: int) -> datetime:
    year, month = divmod(authored_at.year * 12 + authored_at.month - 1 + month_offset, 12)
    return authored_at.replace(year=year, month=month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)


def detect_time_window(
    text: str, authored_at: datetime
) -> tuple[datetime | None, datetime | None, str | None, str | None]:
    lower = text.lower()
    # Calendar intervals are half-open [start, end), preserving the source timezone.
    if "next month" in lower:
        return _month_start(authored_at, 1), _month_start(authored_at, 2), "next month", "month"
    if "next quarter" in lower:
        offset = 3 - (authored_at.month - 1) % 3
        return _month_start(authored_at, offset), _month_start(authored_at, offset + 3), "next quarter", "quarter"
    if "next year" in lower:
        offset = 13 - authored_at.month
        return _month_start(authored_at, offset), _month_start(authored_at, offset + 12), "next year", "year"
    if "later this year" in lower:
        return authored_at, _month_start(authored_at, 13 - authored_at.month), "later this year", "unknown"
    if "in the next couple of weeks" in lower:
        return authored_at, authored_at + timedelta(weeks=2), "in the next couple of weeks", "week"
    return None, None, None, None
