"""Transformer and oracle must derive direction votes from the same shared helper."""

from __future__ import annotations

from dsfs.features.direction import direction_vote


def test_increase_not_negated_is_positive():
    assert direction_vote("INCREASE", False) == 1


def test_increase_negated_is_negative():
    assert direction_vote("INCREASE", True) == -1


def test_decrease_not_negated_is_negative():
    assert direction_vote("DECREASE", False) == -1


def test_decrease_negated_is_positive():
    assert direction_vote("DECREASE", True) == 1


def test_other_values_are_neutral():
    assert direction_vote("STABLE", False) == 0
    assert direction_vote("UNKNOWN", False) == 0
    assert direction_vote("NA", True) == 0


def test_transformer_and_oracle_import_the_same_function():
    from dsfs.features.transformer import _direction_vote as transformer_vote
    from dsfs.forecast.oracle import _direction_from_gt as oracle_vote

    assert transformer_vote is direction_vote
    assert oracle_vote is direction_vote
