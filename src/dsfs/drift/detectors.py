"""Drift detection statistics (docs/10): pure numpy/stdlib, no scipy —
matching the rest of the POC's dependency-light stack.

p-values use standard asymptotic approximations (Kolmogorov for KS, Wilson-
Hilferty for chi-square), not exact distributions — adequate for a POC-level
"is this different enough to investigate" signal, not a precision claim.
"""

from __future__ import annotations

import math

import numpy as np


def ks_two_sample(reference: np.ndarray, monitored: np.ndarray) -> tuple[float, float]:
    """Two-sample KS test. Returns (D statistic, asymptotic two-sided p-value)."""
    a = np.sort(np.asarray(reference, dtype=float))
    b = np.sort(np.asarray(monitored, dtype=float))
    n_a, n_b = len(a), len(b)
    if n_a == 0 or n_b == 0:
        return 0.0, 1.0
    data_all = np.concatenate([a, b])
    cdf_a = np.searchsorted(a, data_all, side="right") / n_a
    cdf_b = np.searchsorted(b, data_all, side="right") / n_b
    d_stat = float(np.max(np.abs(cdf_a - cdf_b)))
    if d_stat == 0.0:
        return 0.0, 1.0

    en = n_a * n_b / (n_a + n_b)
    lam = (math.sqrt(en) + 0.12 + 0.11 / math.sqrt(en)) * d_stat
    p_value = 0.0
    for k in range(1, 101):
        p_value += (-1) ** (k - 1) * math.exp(-2 * (lam ** 2) * (k ** 2))
    p_value = min(max(2 * p_value, 0.0), 1.0)
    return d_stat, p_value


def _chi2_sf_wilson_hilferty(stat: float, df: int) -> float:
    """Wilson-Hilferty approximation to the chi-square survival function."""
    if df <= 0:
        return 1.0
    if stat <= 0:
        return 1.0
    z = (((stat / df) ** (1 / 3)) - (1 - 2 / (9 * df))) / math.sqrt(2 / (9 * df))
    return 0.5 * math.erfc(z / math.sqrt(2))


def chi_square_categorical(
    reference_counts: dict[str, int], monitored_counts: dict[str, int],
) -> tuple[float, float]:
    """Chi-square goodness-of-fit: does monitored's category mix match
    reference's proportions? Returns (statistic, approximate p-value)."""
    categories = sorted(set(reference_counts) | set(monitored_counts))
    total_ref = sum(reference_counts.values())
    total_obs = sum(monitored_counts.values())
    if total_ref == 0 or total_obs == 0 or len(categories) < 2:
        return 0.0, 1.0
    stat = 0.0
    for c in categories:
        expected = reference_counts.get(c, 0) / total_ref * total_obs
        observed = monitored_counts.get(c, 0)
        if expected > 0:
            stat += (observed - expected) ** 2 / expected
    df = len(categories) - 1
    return stat, _chi2_sf_wilson_hilferty(stat, df)


def effect_size_cohens_d(reference: np.ndarray, monitored: np.ndarray) -> float:
    """Standardized mean difference, for the "test AND minimum effect-size"
    alerting rule in docs/10 (a p-value alone is not sufficient)."""
    a = np.asarray(reference, dtype=float)
    b = np.asarray(monitored, dtype=float)
    if len(a) < 2 or len(b) < 2:
        return 0.0
    pooled_std = math.sqrt(((len(a) - 1) * a.var(ddof=1) + (len(b) - 1) * b.var(ddof=1)) / max(len(a) + len(b) - 2, 1))
    if pooled_std == 0:
        return 0.0
    return float((b.mean() - a.mean()) / pooled_std)


def total_variation_distance(reference_counts: dict[str, int], monitored_counts: dict[str, int]) -> float:
    """Categorical effect size: max proportion difference across categories, in [0, 1]."""
    categories = set(reference_counts) | set(monitored_counts)
    total_ref = sum(reference_counts.values())
    total_obs = sum(monitored_counts.values())
    if total_ref == 0 or total_obs == 0:
        return 0.0
    diffs = [
        abs(reference_counts.get(c, 0) / total_ref - monitored_counts.get(c, 0) / total_obs)
        for c in categories
    ]
    return 0.5 * sum(diffs)
