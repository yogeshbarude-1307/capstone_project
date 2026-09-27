"""Pure numpy/stdlib drift detectors (docs/10): KS, chi-square, effect sizes."""

from __future__ import annotations

import numpy as np

from dsfs.drift.detectors import (
    chi_square_categorical,
    effect_size_cohens_d,
    ks_two_sample,
    total_variation_distance,
)


def test_ks_identical_samples_no_drift():
    rng = np.random.RandomState(0)
    a = rng.normal(0, 1, size=500)
    d_stat, p_value = ks_two_sample(a, a.copy())
    assert d_stat == 0.0
    assert p_value == 1.0


def test_ks_clearly_shifted_samples_detected():
    rng = np.random.RandomState(0)
    reference = rng.normal(0, 1, size=500)
    monitored = rng.normal(5, 1, size=500)
    d_stat, p_value = ks_two_sample(reference, monitored)
    assert d_stat > 0.8
    assert p_value < 0.01


def test_ks_empty_input_is_safe():
    d_stat, p_value = ks_two_sample(np.array([]), np.array([1.0, 2.0]))
    assert d_stat == 0.0
    assert p_value == 1.0


def test_chi_square_identical_proportions_not_significant():
    ref = {"a": 100, "b": 100, "c": 100}
    mon = {"a": 100, "b": 100, "c": 100}
    stat, p_value = chi_square_categorical(ref, mon)
    assert stat == 0.0
    assert p_value == 1.0


def test_chi_square_clear_shift_detected():
    ref = {"a": 250, "b": 250, "c": 250, "d": 250}
    mon = {"a": 900, "b": 30, "c": 30, "d": 40}
    stat, p_value = chi_square_categorical(ref, mon)
    assert stat > 20
    assert p_value < 0.01


def test_chi_square_handles_single_category():
    stat, p_value = chi_square_categorical({"a": 10}, {"a": 20})
    assert stat == 0.0
    assert p_value == 1.0


def test_cohens_d_zero_for_identical_distributions():
    rng = np.random.RandomState(1)
    a = rng.normal(0, 1, size=200)
    assert effect_size_cohens_d(a, a.copy()) == 0.0


def test_cohens_d_large_for_shifted_distributions():
    rng = np.random.RandomState(1)
    a = rng.normal(0, 1, size=200)
    b = rng.normal(3, 1, size=200)
    d = effect_size_cohens_d(a, b)
    assert d > 2.0


def test_total_variation_distance_zero_when_identical():
    ref = {"x": 50, "y": 50}
    assert total_variation_distance(ref, ref) == 0.0


def test_total_variation_distance_one_when_fully_disjoint():
    ref = {"x": 100, "y": 0}
    mon = {"x": 0, "y": 100}
    assert total_variation_distance(ref, mon) == 1.0
