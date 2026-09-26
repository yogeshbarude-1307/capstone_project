"""Hand-built labels/predictions for metric arithmetic, independent of rules."""

import hashlib

from dsfs.evaluation.annotations import AnnotatedCase, ExpectedSignal, FIELDS, asserted
from dsfs.models import SignalRecord


def make_case(source_id="one", *, no_signal=False, **expected_overrides):
    text = f"CUST-0001: Demand will increase by 15%. Reference {source_id}."
    defaults = dict(signal_type="DEMAND_EXPECTATION", direction="INCREASE", impact_channel="DEMAND",
                    business_certainty="LIKELY", conditionality="NONE", negated=False,
                    forecast_key="CUST-0001", decision="PASS")
    if no_signal:
        defaults.update(signal_type="NO_SIGNAL", direction="NA", impact_channel="UNKNOWN",
                        business_certainty="UNKNOWN", decision="NO_SIGNAL", abstention_reason="no_signal")
    expected = ExpectedSignal(**(defaults | expected_overrides))
    return AnnotatedCase(
        evidence=dict(source_id=source_id, source_type="account_note", source_record_id=source_id,
                      source_revision="r1", authored_at="2026-01-01T09:00:00Z", available_at="2026-01-01T09:10:00Z",
                      raw_text=text, content_hash="sha256:" + hashlib.sha256(text.encode()).hexdigest(),
                      entity_mentions_raw=["CUST-0001"]),
        scenario_id=source_id, template_group=source_id, split="dev", sample="challenge",
        label_origin="assistant_draft", annotator_ids=["test-draft"], adjudication_state="draft",
        expected=expected,
        field_evidence={name: [dict(source_id=source_id, char_start=0, char_end=len(text))]
                        for name in FIELDS if name != "supersedes_source_id" and asserted(getattr(expected, name))},
    )


def make_prediction(case, **overrides):
    fields = case.expected.model_dump(exclude={"decision", "abstention_reason", "supersedes_source_id"})
    fields.update(signal_id="sig-" + case.evidence.source_id, logical_signal_id="logical-" + case.evidence.source_id,
                  source_id=case.evidence.source_id, source_revision="r1", entity_mentions=["CUST-0001"],
                  evidence_ref=dict(source_id=case.evidence.source_id, char_start=0, char_end=len(case.evidence.raw_text)),
                  extractor_version="test", extraction_config_version="test", extraction_run_id="test-run",
                  extracted_at="2026-01-02T00:00:00Z", record_status="ACTIVE",
                  validation_status="REVIEW" if case.expected.decision == "REVIEW" else "PASS")
    return SignalRecord.model_validate(fields | overrides)
