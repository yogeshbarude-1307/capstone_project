"""Pure-numpy bootstrap CI and paired-permutation tests (docs/08 M9)."""

from __future__ import annotations

import numpy as np
import pytest

from dsfs.evaluation.statistics import (
    bootstrap_ci,
    bootstrap_lift_ci,
    paired_permutation_test,
)


def test_bootstrap_ci_reproducible_given_seed():
    errors = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    a = bootstrap_ci(errors, seed=7)
    b = bootstrap_ci(errors, seed=7)
    assert a == b


def test_bootstrap_ci_point_estimate_is_the_mean():
    errors = np.array([1.0, 2.0, 3.0])
    point, lo, hi = bootstrap_ci(errors, seed=1)
    assert point == pytest.approx(2.0)
    assert lo <= point <= hi


def test_bootstrap_ci_empty_input_returns_nan():
    point, lo, hi = bootstrap_ci(np.array([]))
    assert np.isnan(point)
    assert np.isnan(lo)
    assert np.isnan(hi)


def test_bootstrap_ci_tighter_with_more_data():
    rng = np.random.RandomState(0)
    small = rng.normal(10, 2, size=10)
    large = rng.normal(10, 2, size=1000)
    _, lo_s, hi_s = bootstrap_ci(small, seed=1)
    _, lo_l, hi_l = bootstrap_ci(large, seed=1)
    assert (hi_l - lo_l) < (hi_s - lo_s)


def test_bootstrap_lift_ci_zero_lift_when_identical():
    errors = np.array([5.0, 6.0, 7.0, 8.0])
    point, lo, hi = bootstrap_lift_ci(errors, errors, seed=1)
    assert point == pytest.approx(0.0)


def test_bootstrap_lift_ci_positive_when_enhanced_is_better():
    baseline = np.array([10.0] * 20)
    enhanced = np.array([5.0] * 20)
    point, lo, hi = bootstrap_lift_ci(baseline, enhanced, seed=1)
    assert point == pytest.approx(0.5)
    assert lo > 0  # CI excludes zero — a clear, unambiguous lift


def test_bootstrap_lift_ci_rejects_mismatched_lengths():
    with pytest.raises(ValueError):
        bootstrap_lift_ci(np.array([1.0, 2.0]), np.array([1.0]))


def test_paired_permutation_detects_real_difference():
    rng = np.random.RandomState(0)
    a = rng.normal(10, 1, size=200)
    b = rng.normal(8, 1, size=200)  # clearly different mean, same pairing
    observed, p_value = paired_permutation_test(a, b, seed=1)
    assert observed == pytest.approx(2.0, abs=0.3)
    assert p_value < 0.05


def test_paired_permutation_no_difference_is_not_significant():
    rng = np.random.RandomState(0)
    a = rng.normal(10, 1, size=200)
    b = a.copy()
    observed, p_value = paired_permutation_test(a, b, seed=1)
    assert observed == pytest.approx(0.0)
    assert p_value == 1.0


def test_paired_permutation_rejects_mismatched_lengths():
    with pytest.raises(ValueError):
        paired_permutation_test(np.array([1.0, 2.0]), np.array([1.0]))
