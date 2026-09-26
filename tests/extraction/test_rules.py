from dsfs.extraction.rules import (
    detect_certainty,
    detect_conditionality,
    detect_direction_and_negation,
    detect_magnitude,
    detect_time_window,
)
from dsfs.models.signal_record import BusinessCertainty, Conditionality, Direction, MagnitudeBasis
from datetime import datetime, timedelta


def test_conflicting_direction_cues_are_flagged_not_guessed():
    direction, negated, conflict = detect_direction_and_negation(
        "Customer will increase volume but decrease headcount."
    )
    assert conflict is True
    assert direction == Direction.MIXED


def test_no_direction_cue_returns_none():
    direction, negated, conflict = detect_direction_and_negation("Updated contact email on file.")
    assert direction is None
    assert negated is False
    assert conflict is False


def test_magnitude_percent_is_extracted():
    value, unit, basis = detect_magnitude("Customer confirmed they will increase orders by roughly 15%.")
    assert value == 15.0
    assert unit == "%"
    assert basis == MagnitudeBasis.PERCENT


def test_magnitude_absent_returns_all_none():
    value, unit, basis = detect_magnitude("Customer confirmed they will increase orders.")
    assert (value, unit, basis) == (None, None, None)


def test_conditionality_captures_condition_clause_verbatim():
    conditionality, condition_text = detect_conditionality(
        "Customer may increase volume if the promotion is approved."
    )
    assert conditionality == Conditionality.CONDITIONAL
    assert condition_text == "if the promotion is approved"


def test_conditionality_absent_returns_none():
    conditionality, condition_text = detect_conditionality("Customer confirmed they will increase orders.")
    assert conditionality == Conditionality.NONE
    assert condition_text is None


def test_certainty_phrase_priority_matches_exact_template_forms():
    assert detect_certainty("Customer confirmed they will increase orders.") == BusinessCertainty.ASSERTED
    assert detect_certainty("Customer expects to decrease orders.") == BusinessCertainty.EXPECTED
    assert detect_certainty("Customer will likely increase orders.") == BusinessCertainty.LIKELY
    assert detect_certainty("Customer indicated they might increase orders.") == BusinessCertainty.POSSIBLE
    assert detect_certainty("Customer mentioned they may possibly increase orders.") == BusinessCertainty.UNKNOWN


def test_time_window_is_relative_to_authored_at_not_wall_clock():
    authored_at = datetime(2024, 3, 1)
    start, end, phrase, granularity = detect_time_window("increase orders next quarter.", authored_at)
    assert phrase == "next quarter"
    assert granularity == "quarter"
    assert start == authored_at + timedelta(days=90)
    assert end == start + timedelta(days=90)


def test_time_window_absent_returns_all_none():
    start, end, phrase, granularity = detect_time_window("increase orders.", datetime(2024, 1, 1))
    assert (start, end, phrase, granularity) == (None, None, None, None)
