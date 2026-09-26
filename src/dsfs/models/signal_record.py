"""Signal contract and deterministic cross-field business rules."""

from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from dsfs.models.common import ContractModel, UTCDatetime


class SignalType(StrEnum):
    DEMAND_EXPECTATION = "DEMAND_EXPECTATION"
    PURCHASE_INTENT = "PURCHASE_INTENT"
    ORDER_LIFECYCLE = "ORDER_LIFECYCLE"
    QUANTITY_REVISION = "QUANTITY_REVISION"
    TIMING_REVISION = "TIMING_REVISION"
    INVENTORY_POSITION = "INVENTORY_POSITION"
    COMMERCIAL_EVENT = "COMMERCIAL_EVENT"
    SUPPLY_FULFILLMENT = "SUPPLY_FULFILLMENT"
    MARKET_CONTEXT = "MARKET_CONTEXT"
    OTHER_RELEVANT = "OTHER_RELEVANT"
    NO_SIGNAL = "NO_SIGNAL"


class Direction(StrEnum):
    INCREASE = "INCREASE"
    DECREASE = "DECREASE"
    STABLE = "STABLE"
    MIXED = "MIXED"
    UNKNOWN = "UNKNOWN"
    NA = "NA"


class ImpactChannel(StrEnum):
    DEMAND = "DEMAND"
    FULFILLMENT = "FULFILLMENT"
    MIX_ALLOCATION = "MIX_ALLOCATION"
    UNKNOWN = "UNKNOWN"


class BusinessCertainty(StrEnum):
    ASSERTED = "ASSERTED"
    EXPECTED = "EXPECTED"
    LIKELY = "LIKELY"
    POSSIBLE = "POSSIBLE"
    UNKNOWN = "UNKNOWN"


class Conditionality(StrEnum):
    NONE = "NONE"
    CONDITIONAL = "CONDITIONAL"
    UNKNOWN = "UNKNOWN"


class MagnitudeBasis(StrEnum):
    ABSOLUTE = "ABSOLUTE"
    DELTA = "DELTA"
    PERCENT = "PERCENT"
    RANGE = "RANGE"


class ValidationStatus(StrEnum):
    PASS = "PASS"
    REVIEW = "REVIEW"
    FAIL = "FAIL"


class RecordStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    RETRACTED = "RETRACTED"


class EvidenceRef(ContractModel):
    source_id: str
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)

    @model_validator(mode="after")
    def check_span(self):
        if self.char_end < self.char_start:
            raise ValueError("char_end must be >= char_start")
        return self


class SignalRecord(ContractModel):
    signal_id: str
    logical_signal_id: str
    schema_version: Literal["0.1.0"] = "0.1.0"
    source_id: str
    source_revision: str
    signal_type: SignalType
    signal_subtype: str = "UNKNOWN"
    direction: Direction
    impact_channel: ImpactChannel
    business_certainty: BusinessCertainty
    conditionality: Conditionality
    condition_text: str | None = None
    negated: bool
    magnitude_value: float | None = None
    magnitude_low: float | None = None
    magnitude_high: float | None = None
    magnitude_unit: str | None = None
    magnitude_basis: MagnitudeBasis | None = None
    time_expression_raw: str | None = None
    effective_start: UTCDatetime | None = None
    effective_end: UTCDatetime | None = None
    time_granularity: Literal["day", "week", "month", "quarter", "year", "interval", "unknown"] | None = None
    entity_mentions: list[str] = Field(default_factory=list)
    resolved_entities: list[str] = Field(default_factory=list)
    forecast_key: str | None = None
    evidence_ref: EvidenceRef
    extractor_version: str
    extraction_config_version: str
    extraction_run_id: str
    extracted_at: UTCDatetime
    extraction_confidence: float | None = Field(default=None, ge=0, le=1)
    validation_status: ValidationStatus
    abstention_reason: str | None = None
    record_status: RecordStatus
    supersedes_signal_id: str | None = None
    related_signal_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_business_rules(self):
        if self.signal_type == SignalType.NO_SIGNAL and self.direction != Direction.NA:
            raise ValueError("NO_SIGNAL requires direction=NA")
        if any(v is not None for v in (self.magnitude_value, self.magnitude_low, self.magnitude_high)):
            if not self.magnitude_unit:
                raise ValueError("magnitude_unit is missing")
        if self.magnitude_low is not None and self.magnitude_high is not None:
            if self.magnitude_low > self.magnitude_high:
                raise ValueError("magnitude_high must not precede magnitude_low")
        if self.effective_start is not None and self.effective_end is not None:
            if self.effective_end < self.effective_start:
                raise ValueError("effective_end must not precede effective_start")
        if self.evidence_ref.source_id != self.source_id:
            raise ValueError("evidence_ref must reference the signal's source_id")
        if self.supersedes_signal_id == self.signal_id:
            raise ValueError("a signal cannot supersede itself")
        return self
