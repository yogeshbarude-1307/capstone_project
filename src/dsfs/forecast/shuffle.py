"""Arm D shuffled control: extracted signals reassigned to wrong entity/time (docs/08).

Negative control against leakage or spurious correlation. If arm D improves
over baseline, that signals a PIT bug, a confounding variable, or leakage
in the experiment design — not a real signal.

The shuffling uses a seeded RNG so results are reproducible. Entity keys are
permuted within each cutoff, and cutoff dates are shifted by a random offset,
breaking the true entity-time alignment while preserving the marginal
distribution of feature values.
"""

from __future__ import annotations

import random

import pandas as pd


def shuffle_features(
    features_df: pd.DataFrame,
    *,
    seed: int = 99,
) -> pd.DataFrame:
    """Return a copy of the feature DataFrame with entity/time alignment broken.

    Within each forecast_cutoff, entity_keys are permuted. The feature values
    themselves are unchanged — only the (entity, cutoff) assignment is scrambled.
    """
    if features_df.empty:
        return features_df.copy()
    if features_df["entity_key"].nunique() < 2:
        raise ValueError("Shuffled control is unavailable for a single account")

    rng = random.Random(seed)
    result_rows = []

    groups = ["forecast_cutoff"] + (["horizon_step"] if "horizon_step" in features_df else [])
    for cutoff, group in features_df.groupby(groups):
        rows = group.to_dict("records")
        entities = [r["entity_key"] for r in rows]
        shuffled_entities = entities.copy()
        # A nonzero cyclic offset guarantees a different account for every row.
        offset = rng.randrange(1, len(entities))
        shuffled_entities = entities[offset:] + entities[:offset]
        for row, new_entity in zip(rows, shuffled_entities):
            new_row = row.copy()
            new_row["entity_key"] = new_entity
            new_row["contributing_signal_ids"] = []
            result_rows.append(new_row)

    return pd.DataFrame(result_rows)
