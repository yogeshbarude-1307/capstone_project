"""Reconciliation guard: empty abstention_reason must be blocked cleanly, not by accident."""

from __future__ import annotations

from dsfs.extraction.reconciliation import reconcile_reversal
from dsfs.models import (
    BusinessCertainty,
    Conditionality,
    Direction,
    EvidenceRef,
    ImpactChannel,
    RecordStatus,
    SignalRecord,
    SignalType,
    ValidationStatus,
)

from .conftest import make_evidence


def _reversal_record_with_reason(reason: str | None, forecast_key: str = "CUST-0001") -> SignalRecord:
    ev = make_evidence(
        "rev-1",
        "Previous expansion plan has been cancelled.",
        authored_at="2026-01-07T09:00:00Z",
        available_at="2026-01-07T10:00:00Z",
    )
    return SignalRecord(
        signal_id="sig-rev-r1",
        logical_signal_id="sig-rev",
        source_id=ev.source_id,
        source_revision=ev.source_revision,
        signal_type=SignalType.OTHER_RELEVANT,
        direction=Direction.DECREASE,
        impact_channel=ImpactChannel.DEMAND,
        business_certainty=BusinessCertainty.LIKELY,
        conditionality=Conditionality.NONE,
        negated=False,
        entity_mentions=["CUST-0001"],
        resolved_entities=["CUST-0001"],
        forecast_key=forecast_key,
        evidence_ref=EvidenceRef(source_id=ev.source_id, char_start=0, char_end=20),
        extractor_version="hybrid-v0.1.0",
        extraction_config_version="cfg-v0.1.0",
        extraction_run_id="run-test",
        extracted_at="2026-01-07T10:00:00Z",
        validation_status=ValidationStatus.REVIEW,
        record_status=RecordStatus.ACTIVE,
        abstention_reason=reason,
    )


def test_reversal_with_empty_abstention_reason_is_blocked():
    """Empty reason must NOT accidentally reconcile via the ``set-diff`` bug."""
    ev = make_evidence(
        "rev-1",
        "Previous expansion plan has been cancelled.",
        authored_at="2026-01-07T09:00:00Z",
        available_at="2026-01-07T10:00:00Z",
    )
    record = _reversal_record_with_reason(reason=None)
    result = reconcile_reversal(record, ev, prior=[], sources={})
    assert result is record  # unchanged — no accidental promotion


def test_reversal_with_unrelated_reason_is_blocked():
    ev = make_evidence(
        "rev-1",
        "Previous expansion plan has been cancelled.",
        authored_at="2026-01-07T09:00:00Z",
        available_at="2026-01-07T10:00:00Z",
    )
    record = _reversal_record_with_reason(reason="some unrelated reason")
    result = reconcile_reversal(record, ev, prior=[], sources={})
    assert result is record
