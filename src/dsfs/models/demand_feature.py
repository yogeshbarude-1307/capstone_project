"""Version 1 serving contract: one account, cutoff, and target week."""
from typing import Literal
from pydantic import Field, model_validator
from dsfs.models.forecast_feature import ForecastFeatureRecord, NetDemandDirection
from dsfs.models.common import UTCDatetime

FEATURE_VERSION = "demand-v1"

class DemandFeatureRecord(ForecastFeatureRecord):
    schema_version: Literal["1.0.0"] = "1.0.0"
    feature_definition_version: Literal["demand-v1"] = FEATURE_VERSION
    run_id: str
    horizon_step: int = Field(ge=1, le=4)
    target_start: UTCDatetime
    target_end: UTCDatetime
    signed_pct_change: float | None = None
    active_demand_signal_count: int = Field(default=0, ge=0)
    target_demand_direction: NetDemandDirection = NetDemandDirection.UNKNOWN
    supply_signal_count: int = Field(default=0, ge=0)
    conditional_signal_count: int = Field(default=0, ge=0)
    asserted_signal_count: int = Field(default=0, ge=0)
    expected_signal_count: int = Field(default=0, ge=0)
    likely_signal_count: int = Field(default=0, ge=0)
    possible_signal_count: int = Field(default=0, ge=0)
    tabular_features: dict[str, float] | None
    publication_latency_minutes: float | None = Field(default=None, ge=0)
    freshness_target_minutes: Literal[60] = 60
    freshness_breach: bool = False
    rejected_signal_count: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def check_week(self):
        from datetime import timedelta
        if self.target_start != self.forecast_cutoff + timedelta(weeks=self.horizon_step-1):
            raise ValueError("Target period does not match cutoff and horizon")
        if self.target_end != self.target_start + timedelta(weeks=1):
            raise ValueError("Target period must span one week")
        if self.feature_available_at and self.feature_available_at > self.forecast_cutoff:
            raise ValueError("Feature publication cannot follow its historical cutoff")
        return self
