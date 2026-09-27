"""Annotated effective interval bound must match SignalRecord (>=), not strict >."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from dsfs.evaluation.annotations import ExpectedSignal


def _base_expected(**overrides) -> dict:
    base = dict(
        signal_type="DEMAND_EXPECTATION",
        direction="INCREASE",
        impact_channel="DEMAND",
        business_certainty="LIKELY",
        conditionality="NONE",
        negated=False,
        forecast_key="CUST-0001",
        decision="PASS",
    )
    return base | overrides


def test_zero_length_interval_is_accepted():
    """SignalRecord allows effective_end == effective_start; annotation must too."""
    expected = ExpectedSignal(
        **_base_expected(
            effective_start="2026-02-01T00:00:00Z",
            effective_end="2026-02-01T00:00:00Z",
        )
    )
    assert expected.effective_start == expected.effective_end


def test_end_before_start_still_rejected():
    with pytest.raises(ValidationError, match="on or after start"):
        ExpectedSignal(
            **_base_expected(
                effective_start="2026-02-02T00:00:00Z",
                effective_end="2026-02-01T00:00:00Z",
            )
        )
