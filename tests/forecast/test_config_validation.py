"""ForecastConfig must reject configs that would silently produce wrong training windows."""

from __future__ import annotations

import pytest

from dsfs.forecast.harness import ForecastConfig


def test_default_config_is_valid():
    cfg = ForecastConfig()
    assert cfg.lag_weeks == tuple(sorted(cfg.lag_weeks))


def test_unsorted_lag_weeks_rejected():
    with pytest.raises(ValueError, match="sorted ascending"):
        ForecastConfig(lag_weeks=[4, 1, 2])


def test_nonpositive_lag_weeks_rejected():
    with pytest.raises(ValueError, match="positive"):
        ForecastConfig(lag_weeks=[0, 1, 2])
    with pytest.raises(ValueError, match="positive"):
        ForecastConfig(lag_weeks=[-1, 2])


def test_empty_lag_weeks_rejected():
    with pytest.raises(ValueError, match="empty"):
        ForecastConfig(lag_weeks=[])


def test_nonpositive_horizon_or_train_rejected():
    with pytest.raises(ValueError, match="horizon_weeks"):
        ForecastConfig(horizon_weeks=0)
    with pytest.raises(ValueError, match="train_weeks"):
        ForecastConfig(train_weeks=-5)
