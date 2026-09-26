"""Shared helpers for feature tests."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from dsfs.models.signal_record import (
    BusinessCertainty,
    Conditionality,
    Direction,
    EvidenceRef,
    ImpactChannel,
    MagnitudeBasis,
    RecordStatus,
    SignalRecord,
    SignalType,
    ValidationStatus,
)
from dsfs.models.source_evidence import SourceEvidence, SourceType


def make_signal(
    signal_id: str,
    source_id: str,
    *,
    entity_key: str = "CUST-0001",
    signal_type: SignalType = SignalType.DEMAND_EXPECTATION,
    direction: Direction = Direction.INCREASE,
    negated: bool = False,
    business_certainty: BusinessCertainty = BusinessCertainty.EXPECTED,
    conditionality: Conditionality = Conditionality.NONE,
    magnitude_value: float | None = None,
    magnitude_unit: str | None = None,
    magnitude_basis: MagnitudeBasis | None = None,
    effective_start: str | None = None,
    effective_end: str | None = None,
    record_status: RecordStatus = RecordStatus.ACTIVE,
    validation_status: ValidationStatus = ValidationStatus.PASS,
    extraction_run_id: str = "run-test-001",
) -> SignalRecord:
    return SignalRecord(
        signal_id=signal_id,
        logical_signal_id=signal_id.rsplit("-r", 1)[0] if "-r" in signal_id else signal_id,
        source_id=source_id,
        source_revision="r1",
        signal_type=signal_type,
        direction=direction,
        impact_channel=ImpactChannel.DEMAND,
        business_certainty=business_certainty,
        conditionality=conditionality,
        negated=negated,
        magnitude_value=magnitude_value,
        magnitude_unit=magnitude_unit or ("units" if magnitude_value is not None else None),
        magnitude_basis=magnitude_basis or (MagnitudeBasis.DELTA if magnitude_value is not None else None),
        effective_start=effective_start,
        effective_end=effective_end,
        entity_mentions=["CUST-0001"],
        resolved_entities=[entity_key],
        forecast_key=entity_key,
        evidence_ref=EvidenceRef(source_id=source_id, char_start=0, char_end=10),
        extractor_version="rules-v0.2.0",
        extraction_config_version="cfg-v0.2.0",
        extraction_run_id=extraction_run_id,
        extracted_at="2026-06-01T00:00:00Z",
        validation_status=validation_status,
        record_status=record_status,
    )


def make_source(
    source_id: str,
    available_at: str = "2026-01-10T00:00:00Z",
) -> SourceEvidence:
    return SourceEvidence(
        source_id=source_id,
        source_type=SourceType.ACCOUNT_NOTE,
        source_record_id=source_id,
        source_revision="r1",
        authored_at=available_at,
        available_at=available_at,
        raw_text="test note",
        content_hash="sha256:test",
        entity_mentions_raw=["CUST-0001"],
    )


def utc(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
