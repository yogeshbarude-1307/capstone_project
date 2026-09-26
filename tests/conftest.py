"""Shared fixtures: one valid example record per contract (docs/03-04)."""

from __future__ import annotations

import pytest

from dsfs.models import (
    BusinessCertainty,
    Conditionality,
    Direction,
    EvidenceRef,
    ForecastFeatureRecord,
    ImpactChannel,
    NetDemandDirection,
    RecordStatus,
    SignalRecord,
    SignalType,
    SourceEvidence,
    SourceType,
    StalenessStatus,
    ValidationStatus,
)


@pytest.fixture
def valid_source_evidence() -> SourceEvidence:
    return SourceEvidence(
        source_id="ev-0001",
        source_type=SourceType.ACCOUNT_NOTE,
        source_record_id="acct-note-000123",
        source_revision="r1",
        authored_at="2026-01-05T09:00:00Z",
        available_at="2026-01-05T09:15:00Z",
        raw_text="Customer may increase volume if the promotion is approved.",
        content_hash="sha256:deadbeef",
        entity_mentions_raw=["Acme Corp"],
    )


@pytest.fixture
def valid_signal_record(valid_source_evidence: SourceEvidence) -> SignalRecord:
    return SignalRecord(
        signal_id="sig-0001-r1",
        logical_signal_id="sig-0001",
        source_id=valid_source_evidence.source_id,
        source_revision=valid_source_evidence.source_revision,
        signal_type=SignalType.DEMAND_EXPECTATION,
        signal_subtype="increase",
        direction=Direction.INCREASE,
        impact_channel=ImpactChannel.DEMAND,
        business_certainty=BusinessCertainty.POSSIBLE,
        conditionality=Conditionality.CONDITIONAL,
        condition_text="if the promotion is approved",
        negated=False,
        entity_mentions=["Acme Corp"],
        resolved_entities=["CUST-000123"],
        forecast_key="CUST-000123",
        evidence_ref=EvidenceRef(source_id=valid_source_evidence.source_id, char_start=0, char_end=58),
        extractor_version="hybrid-v0.1.0",
        extraction_config_version="cfg-v0.1.0",
        extraction_run_id="run-2026-01-05T09-16-00",
        extracted_at="2026-01-05T09:16:00Z",
        validation_status=ValidationStatus.PASS,
        record_status=RecordStatus.ACTIVE,
    )


@pytest.fixture
def valid_forecast_feature(valid_signal_record: SignalRecord) -> ForecastFeatureRecord:
    return ForecastFeatureRecord(
        entity_key="CUST-000123",
        forecast_cutoff="2026-01-06T00:00:00Z",
        feature_definition_version="fdv-0.1.0",
        generated_at="2026-01-06T00:05:00Z",
        contributing_signal_ids=[valid_signal_record.signal_id],
        has_active_signal_30d=True,
        signal_count_30d=1,
        net_demand_direction_30d=NetDemandDirection.INCREASE,
        days_since_latest_signal=1,
        feature_available_at="2026-01-06T00:05:00Z",
        staleness_status=StalenessStatus.FRESH,
    )
