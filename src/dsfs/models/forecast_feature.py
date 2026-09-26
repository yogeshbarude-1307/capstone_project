"""Forecast feature contract; additional versioned feature fields are allowed."""

from enum import StrEnum
from typing import Literal

from pydantic import ConfigDict, Field

from dsfs.models.common import ContractModel, UTCDatetime


class NetDemandDirection(StrEnum):
    INCREASE = "INCREASE"
    DECREASE = "DECREASE"
    STABLE = "STABLE"
    MIXED = "MIXED"
    UNKNOWN = "UNKNOWN"


class StalenessStatus(StrEnum):
    FRESH = "FRESH"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"


class ForecastFeatureRecord(ContractModel):
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    entity_key: str
    forecast_cutoff: UTCDatetime
    feature_definition_version: str
    generated_at: UTCDatetime
    contributing_signal_ids: list[str]
    schema_version: Literal["0.1.0"] = "0.1.0"
    has_active_signal_30d: bool | None = None
    signal_count_30d: int | None = Field(default=None, ge=0)
    net_demand_direction_30d: NetDemandDirection | None = None
    expected_qty_delta_next_horizon: float | None = None
    committed_qty: float | None = None
    cancelled_qty_30d: float | None = None
    delay_count_90d: int | None = Field(default=None, ge=0)
    nearest_effective_start_days: int | None = None
    days_since_latest_signal: int | None = Field(default=None, ge=0)
    independent_source_count_30d: int | None = Field(default=None, ge=0)
    active_conflict_count: int | None = Field(default=None, ge=0)
    feature_available_at: UTCDatetime | None = None
    staleness_status: StalenessStatus | None = None
