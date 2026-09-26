"""Orchestrates the deterministic rules + entity-resolution stages into one
SignalRecord per SourceEvidence row, applying abstention wherever evidence is
insufficient rather than guessing (docs/07-extraction-pipeline-design.md).

The local LLM stage (llm_stage.py) is intentionally NOT invoked here by
default -- this function IS the current, documented degradation-path
extractor (rules + NER only). See docs/14-open-questions.md item 1.
"""

from __future__ import annotations

from datetime import datetime, timezone

from dsfs.extraction.entity_resolution import resolve_entities
from dsfs.extraction.rules import (
    detect_certainty,
    detect_conditionality,
    detect_direction_and_negation,
    detect_magnitude,
    detect_time_window,
)
from dsfs.extraction.signal_types import detect_signal_type
from dsfs.models.signal_record import (
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
from dsfs.models.source_evidence import SourceEvidence

DEFAULT_EXTRACTOR_VERSION = "rules-ner-v0.1.0"
DEFAULT_EXTRACTION_CONFIG_VERSION = "cfg-v0.1.0"

_IMPACT_CHANNEL_BY_TYPE: dict[SignalType, ImpactChannel] = {
    SignalType.DEMAND_EXPECTATION: ImpactChannel.DEMAND,
    SignalType.PURCHASE_INTENT: ImpactChannel.DEMAND,
    SignalType.ORDER_LIFECYCLE: ImpactChannel.DEMAND,
    SignalType.QUANTITY_REVISION: ImpactChannel.DEMAND,
    SignalType.TIMING_REVISION: ImpactChannel.DEMAND,
    SignalType.INVENTORY_POSITION: ImpactChannel.DEMAND,
    SignalType.COMMERCIAL_EVENT: ImpactChannel.DEMAND,
    SignalType.MARKET_CONTEXT: ImpactChannel.DEMAND,
    SignalType.SUPPLY_FULFILLMENT: ImpactChannel.FULFILLMENT,
    SignalType.OTHER_RELEVANT: ImpactChannel.UNKNOWN,
    SignalType.NO_SIGNAL: ImpactChannel.UNKNOWN,
}


def extract_signal(
    evidence: SourceEvidence,
    known_entities: set[str],
    *,
    extraction_run_id: str,
    extractor_version: str = DEFAULT_EXTRACTOR_VERSION,
    extraction_config_version: str = DEFAULT_EXTRACTION_CONFIG_VERSION,
    extracted_at: datetime | None = None,
) -> SignalRecord:
    text = evidence.raw_text

    direction, negated, conflict = detect_direction_and_negation(text)
    signal_type = detect_signal_type(text)
    certainty = detect_certainty(text)
    conditionality, condition_text = detect_conditionality(text)
    magnitude_value, magnitude_unit, magnitude_basis = detect_magnitude(text)
    effective_start, effective_end, time_expr, granularity = detect_time_window(text, evidence.authored_at)
    resolved_entities, forecast_key = resolve_entities(evidence.entity_mentions_raw, known_entities)

    validation_status = ValidationStatus.PASS
    abstention_reasons: list[str] = []

    if conflict:
        validation_status = ValidationStatus.REVIEW
        abstention_reasons.append("conflicting direction cues detected in the same note")

    if direction is None and signal_type is None:
        # No cues at all: correctly abstain rather than fabricate a signal.
        signal_type = SignalType.NO_SIGNAL
        direction = Direction.NA
        certainty = BusinessCertainty.UNKNOWN
        conditionality = Conditionality.NONE
        condition_text = None
        magnitude_value = None
        magnitude_unit = None
        magnitude_basis = None
        abstention_reasons.append("no direction or subject-matter cues found in text")
    else:
        if direction is None:
            direction = Direction.UNKNOWN
            validation_status = ValidationStatus.REVIEW
            abstention_reasons.append("subject matter detected but no clear direction cue")
        if signal_type is None:
            signal_type = SignalType.OTHER_RELEVANT
            validation_status = ValidationStatus.REVIEW
            abstention_reasons.append("direction detected but signal type/subject unclear")

    impact_channel = _IMPACT_CHANNEL_BY_TYPE.get(signal_type, ImpactChannel.UNKNOWN)
    abstention_reason = "; ".join(abstention_reasons) if abstention_reasons else None

    evidence_ref = EvidenceRef(source_id=evidence.source_id, char_start=0, char_end=len(text))

    return SignalRecord(
        signal_id=f"sig-{evidence.source_id}-r1",
        logical_signal_id=f"sig-{evidence.source_id}",
        source_id=evidence.source_id,
        source_revision=evidence.source_revision,
        signal_type=signal_type,
        signal_subtype=direction.value.lower(),
        direction=direction,
        impact_channel=impact_channel,
        business_certainty=certainty,
        conditionality=conditionality,
        condition_text=condition_text,
        negated=negated,
        magnitude_value=magnitude_value,
        magnitude_unit=magnitude_unit,
        magnitude_basis=magnitude_basis,
        time_expression_raw=time_expr,
        effective_start=effective_start,
        effective_end=effective_end,
        time_granularity=granularity,
        entity_mentions=evidence.entity_mentions_raw,
        resolved_entities=resolved_entities,
        forecast_key=forecast_key,
        evidence_ref=evidence_ref,
        extractor_version=extractor_version,
        extraction_config_version=extraction_config_version,
        extraction_run_id=extraction_run_id,
        extracted_at=extracted_at or datetime.now(timezone.utc),
        extraction_confidence=None,  # rules stage: no calibrated probability; never conflate with business_certainty
        validation_status=validation_status,
        abstention_reason=abstention_reason,
        record_status=RecordStatus.ACTIVE,
    )
