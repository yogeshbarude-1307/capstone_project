"""Oracle interpretations feed the same aggregation and publication service."""
from dsfs.features.service import DemandFeatureService
from dsfs.models.signal_record import (SignalRecord, EvidenceRef, SignalType, Direction,
    ImpactChannel, ValidationStatus, RecordStatus, MagnitudeBasis)

def oracle_service(d0, ground_truth, sources, run_id, *, delays=None, forecast_config=None):
    signals = []
    first_by_event = {}
    for gt in sorted(ground_truth, key=lambda g: (sources[g.source_id].available_at, g.source_id)):
        src = sources[gt.source_id]
        sid = "oracle-" + gt.source_id
        target = first_by_event.get(gt.supersedes_event_id)
        kind = SignalType.NO_SIGNAL if gt.is_irrelevant else gt.signal_type
        record = SignalRecord(
            signal_id=sid, logical_signal_id=sid, business_event_ref=gt.event_id or gt.supersedes_event_id,
            source_id=src.source_id, source_revision=src.source_revision,
            signal_type=kind, direction=Direction.NA if gt.is_irrelevant else gt.direction,
            impact_channel=(ImpactChannel.FULFILLMENT if kind in (SignalType.SUPPLY_FULFILLMENT, SignalType.MARKET_CONTEXT)
                            else ImpactChannel.DEMAND),
            business_certainty=gt.business_certainty, conditionality=gt.conditionality,
            condition_text=gt.condition_text, negated=gt.negated,
            magnitude_value=gt.stated_magnitude_value, magnitude_unit=gt.stated_magnitude_unit,
            magnitude_basis=MagnitudeBasis.PERCENT if gt.stated_magnitude_unit == "%" else None,
            effective_start=gt.effective_start, effective_end=gt.effective_end,
            forecast_key=gt.entity_key, entity_mentions=[], resolved_entities=[gt.entity_key] if gt.entity_key else [],
            evidence_ref=EvidenceRef(source_id=src.source_id, char_start=0, char_end=len(src.raw_text)),
            extractor_version="oracle-v1", extraction_config_version="oracle-v1", extraction_run_id=run_id,
            extracted_at=src.available_at, validation_status=ValidationStatus.PASS,
            record_status=RecordStatus.ACTIVE, supersedes_signal_id=target if gt.is_reversal else None,
        )
        signals.append(record)
        if gt.event_id:
            first_by_event.setdefault(gt.event_id, sid)
    return DemandFeatureService(d0, signals, sources, run_id, delays=delays, forecast_config=forecast_config)
