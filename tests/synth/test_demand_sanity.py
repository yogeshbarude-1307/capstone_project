"""Milestone 2 acceptance test: "a distributional sanity check on D0 (no
negative demand, plausible seasonality)."""

from __future__ import annotations

import random

import numpy as np
import pytest

from dsfs.synth.config import GeneratorConfig
from dsfs.synth.demand import realize_demand
from dsfs.synth.entities import generate_entities
from dsfs.synth.latent import generate_latent_events


@pytest.fixture
def d0():
    config = GeneratorConfig(seed=11, n_entities=10, n_weeks=104)
    rng = random.Random(config.seed)
    entities = generate_entities(config)
    _, hidden_states = generate_latent_events(entities, config, rng)
    return realize_demand(entities, hidden_states, config, random.Random(config.seed + 2))


def test_no_negative_demand(d0):
    assert (d0["demand"] >= 0).all()


def test_demand_is_finite(d0):
    assert np.isfinite(d0["demand"]).all()


def test_every_entity_has_every_week(d0):
    config = GeneratorConfig(seed=11, n_entities=10, n_weeks=104)
    entities = generate_entities(config)
    assert set(d0["entity_key"].unique()) == set(entities)
    for entity in entities:
        rows = d0[d0["entity_key"] == entity]
        assert len(rows) == config.n_weeks
        assert sorted(rows["week_index"]) == list(range(config.n_weeks))


def test_seasonality_is_plausible(d0):
    """A crude but meaningful check: with seasonal_period_weeks=52 and two
    years of data, the correlation between demand at week i and week i+52
    (same entity) should be positive on average — i.e. the series
    genuinely repeats on an annual cycle rather than being pure noise."""
    config = GeneratorConfig(seed=11, n_entities=10, n_weeks=104)
    correlations = []
    for entity in d0["entity_key"].unique():
        series = d0[d0["entity_key"] == entity].sort_values("week_index")["demand"].to_numpy()
        period = config.seasonal_period_weeks
        if len(series) <= period:
            continue
        a = series[: len(series) - period]
        b = series[period:]
        if np.std(a) > 0 and np.std(b) > 0:
            correlations.append(np.corrcoef(a, b)[0, 1])
    assert correlations, "no entity had enough history to test seasonality"
    assert np.mean(correlations) > 0, (
        f"expected positive average year-over-year autocorrelation, got {np.mean(correlations):.3f}"
    )


def test_demand_has_nonzero_variance_per_entity(d0):
    for entity in d0["entity_key"].unique():
        series = d0[d0["entity_key"] == entity]["demand"]
        assert series.std() > 0, f"{entity} has a degenerate constant demand series"
