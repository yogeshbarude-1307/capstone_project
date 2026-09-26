"""Immutable source evidence matching source_evidence.schema.json."""

from enum import StrEnum
from typing import Literal

from pydantic import ConfigDict, Field, model_validator

from dsfs.models.common import ContractModel, UTCDatetime


class SourceType(StrEnum):
    ACCOUNT_NOTE = "account_note"
    SERVICE_NOTE = "service_note"
    SUPPLIER_COMMENTARY = "supplier_commentary"
    SALES_COMMENTARY = "sales_commentary"
    OTHER = "other"


class SourceEvidence(ContractModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str
    source_type: SourceType
    source_record_id: str
    source_revision: str
    authored_at: UTCDatetime
    available_at: UTCDatetime
    raw_text: str = ""
    content_hash: str
    entity_mentions_raw: list[str] = Field(default_factory=list)
    schema_version: Literal["0.1.0"] = "0.1.0"

    @model_validator(mode="after")
    def check_availability(self):
        if self.available_at < self.authored_at:
            raise ValueError("available_at must not be earlier than authored_at")
        return self
