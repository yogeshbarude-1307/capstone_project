"""Versioned D2 annotations, provenance, evidence spans, and split validation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from dsfs.models import BusinessCertainty, Conditionality, Direction, EvidenceRef, ImpactChannel, SignalType, SourceEvidence
from dsfs.models.common import ContractModel, UTCDatetime

FieldName = Literal[
    "signal_type", "direction", "impact_channel", "business_certainty", "conditionality",
    "condition_text", "negated", "magnitude_value", "magnitude_unit",
    "effective_start", "effective_end", "forecast_key", "supersedes_source_id",
]
FIELDS = list(FieldName.__args__)


def asserted(value: object) -> bool:
    """Unknown/absent values are not positive assertions for grounding or PR."""
    return value is not None and value is not False and value not in ("UNKNOWN", "NA", "NONE", "NO_SIGNAL")


class ExpectedSignal(ContractModel):
    signal_type: SignalType
    direction: Direction
    impact_channel: ImpactChannel
    business_certainty: BusinessCertainty
    conditionality: Conditionality
    condition_text: str | None = None
    negated: bool
    magnitude_value: float | None = None
    magnitude_unit: str | None = None
    effective_start: UTCDatetime | None = None
    effective_end: UTCDatetime | None = None
    forecast_key: str | None = None
    supersedes_source_id: str | None = None
    decision: Literal["PASS", "NO_SIGNAL", "REVIEW"]
    abstention_reason: str | None = None

    @model_validator(mode="after")
    def check_interpretation(self):
        if self.signal_type == SignalType.NO_SIGNAL and self.direction != Direction.NA:
            raise ValueError("NO_SIGNAL requires direction=NA")
        if (self.decision == "NO_SIGNAL") != (self.signal_type == SignalType.NO_SIGNAL):
            raise ValueError("NO_SIGNAL decision and type must agree")
        if self.decision != "PASS" and not self.abstention_reason:
            raise ValueError("Abstentions require an annotation reason")
        if self.magnitude_value is not None and not self.magnitude_unit:
            raise ValueError("Annotated magnitude requires a unit")
        if self.effective_start and self.effective_end and self.effective_end <= self.effective_start:
            raise ValueError("Annotated interval must have positive duration")
        return self


class AnnotatedCase(ContractModel):
    evidence: SourceEvidence
    scenario_id: str
    template_group: str
    split: Literal["train", "dev", "test"]
    sample: Literal["challenge", "natural_prevalence"]
    tags: list[str] = Field(default_factory=list)
    label_origin: Literal["assistant_draft", "human"]
    annotator_ids: list[str] = Field(min_length=1)
    adjudication_state: Literal["draft", "single", "agreed", "resolved"]
    adjudicator_id: str | None = None
    ambiguity_flag: bool = False
    expected: ExpectedSignal
    scored_fields: list[FieldName] = Field(default_factory=lambda: FIELDS.copy())
    field_evidence: dict[FieldName, list[EvidenceRef]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def check_annotation(self):
        if len(set(self.annotator_ids)) != len(self.annotator_ids):
            raise ValueError("Annotator IDs must be distinct")
        if self.label_origin == "assistant_draft" and self.adjudication_state != "draft":
            raise ValueError("Assistant draft labels cannot claim human adjudication")
        if self.adjudication_state in ("agreed", "resolved") and len(self.annotator_ids) < 2:
            raise ValueError("Double annotation requires two distinct annotators")
        if self.adjudication_state == "resolved" and not self.adjudicator_id:
            raise ValueError("Resolved disagreements require an adjudicator")
        if len(set(self.scored_fields)) != len(self.scored_fields):
            raise ValueError("scored_fields contains duplicates")
        for name in self.scored_fields:
            # Supersession is scored against linked source identity, separately from
            # field grounding because it can depend on previous notes in the scenario.
            if name != "supersedes_source_id" and asserted(getattr(self.expected, name)):
                if not self.field_evidence.get(name):
                    raise ValueError(f"Annotated assertion {name} needs evidence spans")
        for spans in self.field_evidence.values():
            for span in spans:
                if span.source_id != self.evidence.source_id or not (
                    0 <= span.char_start < span.char_end <= len(self.evidence.raw_text)
                ):
                    raise ValueError("Annotation span must reference nonempty text in its own source")
        digest = "sha256:" + hashlib.sha256(self.evidence.raw_text.encode("utf-8")).hexdigest()
        if self.evidence.content_hash != digest:
            raise ValueError("Evidence content_hash does not match raw_text")
        return self


class AnnotationDataset(ContractModel):
    schema_version: Literal["d2-0.1.0"] = "d2-0.1.0"
    dataset_id: str
    description: str
    known_entities: list[str]
    cases: list[AnnotatedCase] = Field(min_length=1)

    @model_validator(mode="after")
    def check_dataset(self):
        sources = {c.evidence.source_id: c for c in self.cases}
        if len(sources) != len(self.cases):
            raise ValueError("Duplicate source IDs in D2")
        partitions: dict[tuple[str, str], tuple[str, str]] = {}
        texts: dict[str, str] = {}
        for case in self.cases:
            for kind, key in (("scenario", case.scenario_id), ("template", case.template_group)):
                partition = (case.split, case.sample)
                if partitions.setdefault((kind, key), partition) != partition:
                    raise ValueError("Scenario/template group crosses a split or sample boundary")
            # Exact duplicate text cannot leak across train/dev/test, even under a new group.
            normalized = " ".join(case.evidence.raw_text.casefold().split())
            if texts.setdefault(normalized, case.split) != case.split:
                raise ValueError("Duplicate text crosses a split boundary")
            if case.expected.forecast_key and case.expected.forecast_key not in self.known_entities:
                raise ValueError("Expected forecast_key is missing from master entities")
            target_id = case.expected.supersedes_source_id
            if target_id:
                target = sources.get(target_id)
                if target is None or target.scenario_id != case.scenario_id or target_id == case.evidence.source_id:
                    raise ValueError("Supersession must reference a different source in the same scenario")
                if target.evidence.available_at > case.evidence.authored_at:
                    raise ValueError("Supersession label references unavailable future evidence")
        return self


def load_dataset(path: Path) -> AnnotationDataset:
    return AnnotationDataset.model_validate_json(path.read_text(encoding="utf-8"))


def snapshot_payload(dataset: AnnotationDataset) -> dict:
    payload = dataset.model_dump(mode="json")
    payload["cases"] = sorted(payload["cases"], key=lambda c: c["evidence"]["source_id"])
    return payload


def snapshot_hash(dataset: AnnotationDataset) -> str:
    payload = snapshot_payload(dataset)
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
