"""Conservative within-run reversal linking, using only earlier source evidence.

No generator ground truth is used. An ambiguous reference remains REVIEW.
Physical ledger rows are immutable; the historical view derives supersession.
"""

from dsfs.extraction.rules import is_reversal
from dsfs.models.signal_record import RecordStatus, SignalRecord, SignalType, ValidationStatus
from dsfs.models.source_evidence import SourceEvidence


def reconcile_reversal(
    record: SignalRecord,
    evidence: SourceEvidence,
    prior: list[SignalRecord],
    sources: dict[str, SourceEvidence],
) -> SignalRecord:
    if not is_reversal(evidence.raw_text) or record.forecast_key is None:
        return record
    allowed_reasons = {
        "reversal requires an unambiguous prior signal",
        "direction detected but signal type/subject unclear",
    }
    reason_parts = {r for r in (record.abstention_reason or "").split("; ") if r}
    if not reason_parts or reason_parts - allowed_reasons:
        return record
    # The referenced claim must have been available when the reversal was authored,
    # not merely by the time the entire batch happens to be processed.
    known = [p for p in prior if sources[p.source_id].available_at <= evidence.authored_at]
    superseded = {p.supersedes_signal_id for p in known if p.validation_status == ValidationStatus.PASS}
    candidates = [p for p in known if (
        p.signal_id not in superseded
        and p.record_status == RecordStatus.ACTIVE
        and p.validation_status == ValidationStatus.PASS
        and not p.negated
        and p.signal_type != SignalType.NO_SIGNAL
        and p.forecast_key == record.forecast_key
        and (record.signal_type == SignalType.OTHER_RELEVANT or p.signal_type == record.signal_type)
        and (p.effective_end is None or p.effective_end > evidence.authored_at)
        and (record.business_event_ref is None or p.business_event_ref == record.business_event_ref)
    )]
    if record.business_event_ref and candidates:
        # Repeated notes for the same explicitly referenced event form one claim.
        candidates = [max(candidates, key=lambda p: (sources[p.source_id].available_at, p.signal_id))]
    if len(candidates) != 1:
        return record
    target = candidates[0]
    data = record.model_dump()
    data.update(
        signal_type=target.signal_type,
        signal_subtype="cancelled",
        impact_channel=target.impact_channel,
        supersedes_signal_id=target.signal_id,
        related_signal_ids=[target.signal_id],
        validation_status=ValidationStatus.PASS,
        abstention_reason=None,
    )
    return SignalRecord.model_validate(data)
