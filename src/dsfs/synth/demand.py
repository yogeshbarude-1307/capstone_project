"""Step 4 of the causal generation order (docs/06-synthetic-data-design.md):
realize demand INDEPENDENTLY of, and strictly AFTER, note rendering.

realize_demand() takes ONLY HiddenState objects (never Knowable, never any
rendered text or extracted structure). This module must never import
dsfs.synth.notes — that import-direction constraint is asserted directly in
tests/synth/test_leakage.py, in addition to the runtime isinstance guard
below.
"""

from __future__ import annotations

import math
import random
from datetime import date, timedelta

import pandas as pd

from dsfs.synth.config import GeneratorConfig
from dsfs.synth.latent import HiddenState, Knowable
from dsfs.models.common import as_utc


def realize_demand(
    entities: list[str],
    hidden_states: list[HiddenState],
    config: GeneratorConfig,
    rng: random.Random,
) -> pd.DataFrame:
    """Build the D0 weekly demand history.

    Materialization (whether a hidden business intent actually turns into
    realized demand) is sampled HERE, using its own independent rng, using
    only HiddenState fields — never rendered note text, never a structured
    extraction result, never
    whatever notes.generate_notes() happened to render.
    """
    for hs in hidden_states:
        if isinstance(hs, Knowable):  # pragma: no cover - defensive, see test_leakage.py
            raise TypeError(
                "realize_demand() received a Knowable where a HiddenState was expected. "
                "Demand realization must never see the knowable/note-facing representation."
            )

    per_entity_params = {
        entity_key: {
            "level": rng.uniform(*config.weekly_baseline_level_range),
            "trend_frac": rng.uniform(*config.weekly_trend_frac_range),
            "phase": rng.uniform(0, 2 * math.pi),
        }
        for entity_key in entities
    }

    realized_deltas: dict[str, tuple[bool, float]] = {}
    for hs in hidden_states:
        p_materialize = config.materialization_prob_by_certainty.get(hs.business_certainty.value, 0.5)
        materializes = rng.random() < p_materialize
        if materializes and hs.true_demand_delta_frac != 0.0:
            noise = rng.gauss(0.0, config.realized_magnitude_noise_frac * abs(hs.true_demand_delta_frac))
            realized_frac = hs.true_demand_delta_frac + noise
        else:
            realized_frac = 0.0
        realized_deltas[hs.event_id] = (materializes, realized_frac)

    hidden_by_entity: dict[str, list[HiddenState]] = {e: [] for e in entities}
    for hs in hidden_states:
        hidden_by_entity.setdefault(hs.entity_key, []).append(hs)

    rows: list[dict] = []
    for entity_key in entities:
        params = per_entity_params[entity_key]
        entity_events = hidden_by_entity.get(entity_key, [])

        for week_index in range(config.n_weeks):
            period_start = date_from_week(config.start_date, week_index)
            week_start_dt = _to_datetime(period_start)
            week_end_dt = week_start_dt + timedelta(days=7)

            trend_component = params["level"] * params["trend_frac"] * week_index
            seasonal_component = (
                params["level"]
                * config.seasonal_amplitude_frac
                * math.sin(2 * math.pi * week_index / config.seasonal_period_weeks + params["phase"])
            )
            level_t = params["level"] + trend_component + seasonal_component

            event_delta = 0.0
            for hs in entity_events:
                _, realized_frac = realized_deltas[hs.event_id]
                if realized_frac == 0.0:
                    continue
                end = min(as_utc(hs.effective_end), as_utc(hs.cancellation_at)) if hs.cancellation_at else as_utc(hs.effective_end)
                overlap = max(0.0, (min(end, week_end_dt)-max(as_utc(hs.effective_start), week_start_dt)).total_seconds())
                event_delta += level_t * realized_frac * overlap / (7 * 86400)

            noise_factor = 1.0 + rng.gauss(0.0, config.demand_noise_frac)
            demand = max(0.0, (level_t + event_delta) * noise_factor)

            rows.append(
                {
                    "entity_key": entity_key,
                    "period_start": period_start,
                    "week_index": week_index,
                    "demand": round(demand, 2),
                }
            )

    return pd.DataFrame(rows)


def date_from_week(start_date: date, week_index: int) -> date:
    return start_date + timedelta(weeks=week_index)


def _to_datetime(d: date):
    from datetime import datetime

    return as_utc(datetime.combine(d, datetime.min.time()))
