"""Result segmentation for M9 (docs/08): per-horizon and signal-exposed-subset
breakdowns, built only from what the generator/harness actually produce.

Per-generator-segment (e.g. product family, customer tier), entity-resolved-
only, and early-signal subsets are NOT implemented here: the synthetic
generator does not define a product family/customer tier, and threading
entity-resolution status or signal-lead-time through to forecast origins is
follow-up scope, not fabricated in this POC. See docs/16-revised-execution-plan.md.
"""

from __future__ import annotations

from collections import defaultdict

import pandas as pd

from dsfs.forecast.harness import OriginResult, normalize_cutoff_column


def per_horizon(origins: list[OriginResult]) -> dict[int, list[OriginResult]]:
    """Group origins by horizon step h = horizon_week_index - origin_week_index."""
    grouped: dict[int, list[OriginResult]] = defaultdict(list)
    for o in origins:
        h = o.horizon_week_index - o.origin_week_index
        grouped[h].append(o)
    return dict(sorted(grouped.items()))


def signal_exposed_subset(
    origins: list[OriginResult], signal_features: pd.DataFrame | None,
) -> list[OriginResult]:
    """Origins where a signal was actually active at that exact (entity_key,
    origin_cutoff) — an exact match, not an entity-level approximation."""
    if signal_features is None or signal_features.empty or "has_active_signal_30d" not in signal_features.columns:
        return []
    signal_features = normalize_cutoff_column(signal_features)
    exposed = signal_features.loc[signal_features["has_active_signal_30d"] == True]  # noqa: E712
    exposed_keys = set(zip(exposed["entity_key"], exposed["forecast_cutoff"]))
    if not exposed_keys:
        return []
    return [o for o in origins if (o.entity_key, o.origin_cutoff) in exposed_keys]
