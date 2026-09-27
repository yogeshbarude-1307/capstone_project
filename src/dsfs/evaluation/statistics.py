"""Pure-numpy bootstrap CI and paired-permutation tests (docs/08 M9).

No scipy dependency, matching the rest of the POC's numpy-only forecast stack.
"""

from __future__ import annotations

import numpy as np


def bootstrap_ci(
    errors: np.ndarray, *, n_resamples: int = 1000, seed: int = 42, alpha: float = 0.05,
) -> tuple[float, float, float]:
    """Bootstrap CI for the mean of ``errors``. Returns (point, ci_low, ci_high)."""
    errors = np.asarray(errors, dtype=float)
    point = float(errors.mean()) if len(errors) else float("nan")
    if len(errors) == 0:
        return point, float("nan"), float("nan")
    rng = np.random.RandomState(seed)
    n_obs = len(errors)
    boot_means = np.empty(n_resamples)
    for i in range(n_resamples):
        idx = rng.randint(0, n_obs, size=n_obs)
        boot_means[i] = errors[idx].mean()
    lo, hi = np.percentile(boot_means, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return point, float(lo), float(hi)


def bootstrap_lift_ci(
    baseline_errors: np.ndarray,
    enhanced_errors: np.ndarray,
    *,
    n_resamples: int = 1000,
    seed: int = 42,
    alpha: float = 0.05,
) -> tuple[float, float, float]:
    """Paired bootstrap CI for incremental lift = (baseline_mae - enhanced_mae) / baseline_mae.

    Both arrays must be the same length and index-aligned (same origins).
    """
    baseline_errors = np.asarray(baseline_errors, dtype=float)
    enhanced_errors = np.asarray(enhanced_errors, dtype=float)
    if len(baseline_errors) != len(enhanced_errors):
        raise ValueError("baseline_errors and enhanced_errors must be the same length (paired)")
    n_obs = len(baseline_errors)
    if n_obs == 0:
        return float("nan"), float("nan"), float("nan")

    def _lift(b: np.ndarray, e: np.ndarray) -> float:
        b_mean = b.mean()
        return (b_mean - e.mean()) / b_mean if b_mean else 0.0

    point = _lift(baseline_errors, enhanced_errors)
    rng = np.random.RandomState(seed)
    lifts = np.empty(n_resamples)
    for i in range(n_resamples):
        idx = rng.randint(0, n_obs, size=n_obs)
        lifts[i] = _lift(baseline_errors[idx], enhanced_errors[idx])
    lo, hi = np.percentile(lifts, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return point, float(lo), float(hi)


def paired_permutation_test(
    a_errors: np.ndarray, b_errors: np.ndarray, *, n_resamples: int = 1000, seed: int = 42,
) -> tuple[float, float]:
    """Sign-flip paired permutation test for H0: mean(a_errors) == mean(b_errors).

    Returns (observed_mean_difference, two_sided_p_value).
    """
    a_errors = np.asarray(a_errors, dtype=float)
    b_errors = np.asarray(b_errors, dtype=float)
    if len(a_errors) != len(b_errors):
        raise ValueError("a_errors and b_errors must be the same length (paired)")
    diffs = a_errors - b_errors
    observed = float(diffs.mean())
    if len(diffs) == 0:
        return observed, float("nan")
    rng = np.random.RandomState(seed)
    n_obs = len(diffs)
    count = 0
    for _ in range(n_resamples):
        signs = rng.choice(np.array([-1.0, 1.0]), size=n_obs)
        stat = (diffs * signs).mean()
        if abs(stat) >= abs(observed):
            count += 1
    p_value = (count + 1) / (n_resamples + 1)
    return observed, float(p_value)
