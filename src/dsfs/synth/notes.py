"""Step 3 of the causal generation order (docs/06-synthetic-data-design.md):
render note text from Knowable ONLY, and record the generator's own ground
truth in a SEPARATE object.

This module must never import dsfs.synth.demand and must never receive a
HiddenState (enforced by an isinstance guard below, and by an import-graph
test in tests/synth/test_leakage.py). NoteGroundTruth is intentionally NOT
one of the three canonical pipeline contracts in docs/schemas/ — it is
generator-internal truth (docs/06), used later only to build the "oracle"
arm of the forecasting experiment (docs/08), never as a substitute for the
extraction pipeline (Milestone 3) or for D2 human annotation.
"""

from __future__ import annotations

import hashlib
import random
import uuid
from datetime import datetime, timedelta

from pydantic import BaseModel, ConfigDict

from dsfs.models.signal_record import BusinessCertainty, Conditionality, Direction, SignalType
from dsfs.models.source_evidence import SourceEvidence, SourceType
from dsfs.synth import templates
from dsfs.synth.config import GeneratorConfig
from dsfs.synth.latent import HiddenState, Knowable

_SOURCE_TYPES = [
    SourceType.ACCOUNT_NOTE,
    SourceType.SERVICE_NOTE,
    SourceType.SUPPLIER_COMMENTARY,
    SourceType.SALES_COMMENTARY,
]


class NoteGroundTruth(BaseModel):
    """Generator-internal oracle truth for one rendered note.

    Joined to its SourceEvidence by source_id only — never embedded in the
    note text or in SourceEvidence itself, preserving the evidence/ground
    truth separation described in docs/06-synthetic-data-design.md.
    """

    model_config = ConfigDict(extra="forbid")

    source_id: str
    event_id: str | None  # null for irrelevant/no-signal notes
    signal_type: SignalType
    direction: Direction
    business_certainty: BusinessCertainty
    conditionality: Conditionality
    condition_text: str | None
    stated_magnitude_value: float | None
    stated_magnitude_unit: str | None
    effective_start: datetime | None
    effective_end: datetime | None
    negated: bool
    is_irrelevant: bool
    is_reversal: bool
    supersedes_event_id: str | None
    template_id: str


def _content_hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sample_authored_at(knowable_from: datetime, effective_start: datetime, rng: random.Random) -> datetime:
    span_days = max((effective_start - knowable_from).days, 0)
    offset_days = rng.randint(0, span_days) if span_days > 0 else 0
    offset_seconds = rng.randint(0, 24 * 3600 - 1)
    return knowable_from + timedelta(days=offset_days, seconds=offset_seconds)


def _sample_available_at(authored_at: datetime, config: GeneratorConfig, rng: random.Random) -> datetime:
    delay_minutes = rng.randint(*config.ingestion_delay_minutes_range)
    return authored_at + timedelta(minutes=delay_minutes)


def _new_source_id() -> str:
    return f"EV-{uuid.uuid4().hex[:12]}"


def generate_notes(
    knowables: list[Knowable],
    config: GeneratorConfig,
    rng: random.Random,
) -> tuple[list[SourceEvidence], list[NoteGroundTruth]]:
    for k in knowables:
        if isinstance(k, HiddenState):  # pragma: no cover - defensive, see test_leakage.py
            raise TypeError(
                "generate_notes() received a HiddenState where a Knowable was expected. "
                "Note rendering must never see the hidden, outcome-bearing representation."
            )

    evidence_rows: list[SourceEvidence] = []
    ground_truth_rows: list[NoteGroundTruth] = []

    for k in knowables:
        n_notes = rng.randint(*config.notes_per_event_range)
        use_negation = k.direction == Direction.STABLE and rng.random() < 0.5

        for _ in range(n_notes):
            authored_at = _sample_authored_at(k.knowable_from, k.effective_start, rng)
            available_at = _sample_available_at(authored_at, config, rng)
            source_id = _new_source_id()

            if use_negation:
                text = templates.render_negation_note(
                    signal_type=k.signal_type, authored_at=authored_at, effective_start=k.effective_start, rng=rng
                )
                template_id = "negation"
                negated = True
            else:
                text = templates.render_standard_note(
                    signal_type=k.signal_type,
                    direction=k.direction,
                    business_certainty=k.business_certainty,
                    conditionality=k.conditionality,
                    condition_text=k.condition_text,
                    stated_magnitude_value=k.stated_magnitude_value,
                    stated_magnitude_unit=k.stated_magnitude_unit,
                    authored_at=authored_at,
                    effective_start=k.effective_start,
                    rng=rng,
                )
                template_id = "standard"
                negated = False

            evidence_rows.append(
                SourceEvidence(
                    source_id=source_id,
                    source_type=rng.choice(_SOURCE_TYPES),
                    source_record_id=source_id,
                    source_revision="r1",
                    authored_at=authored_at,
                    available_at=available_at,
                    raw_text=text,
                    content_hash=_content_hash(text),
                    entity_mentions_raw=[k.entity_key],
                )
            )
            ground_truth_rows.append(
                NoteGroundTruth(
                    source_id=source_id,
                    event_id=k.event_id,
                    signal_type=k.signal_type,
                    direction=k.direction,
                    business_certainty=k.business_certainty,
                    conditionality=k.conditionality,
                    condition_text=k.condition_text,
                    stated_magnitude_value=k.stated_magnitude_value,
                    stated_magnitude_unit=k.stated_magnitude_unit,
                    effective_start=k.effective_start,
                    effective_end=k.effective_end,
                    negated=negated,
                    is_irrelevant=False,
                    is_reversal=False,
                    supersedes_event_id=None,
                    template_id=template_id,
                )
            )

        if rng.random() < config.reversal_probability:
            reversal_authored_at = k.effective_start + timedelta(days=rng.randint(1, 21))
            reversal_available_at = _sample_available_at(reversal_authored_at, config, rng)
            reversal_source_id = _new_source_id()
            reversal_text = templates.render_reversal_note(
                original_signal_type=k.signal_type, authored_at=reversal_authored_at, rng=rng
            )
            evidence_rows.append(
                SourceEvidence(
                    source_id=reversal_source_id,
                    source_type=rng.choice(_SOURCE_TYPES),
                    source_record_id=reversal_source_id,
                    source_revision="r1",
                    authored_at=reversal_authored_at,
                    available_at=reversal_available_at,
                    raw_text=reversal_text,
                    content_hash=_content_hash(reversal_text),
                    entity_mentions_raw=[k.entity_key],
                )
            )
            ground_truth_rows.append(
                NoteGroundTruth(
                    source_id=reversal_source_id,
                    event_id=None,
                    signal_type=k.signal_type,
                    direction=Direction.STABLE,
                    business_certainty=BusinessCertainty.ASSERTED,
                    conditionality=Conditionality.NONE,
                    condition_text=None,
                    stated_magnitude_value=None,
                    stated_magnitude_unit=None,
                    effective_start=k.effective_start,
                    effective_end=k.effective_end,
                    negated=True,
                    is_irrelevant=False,
                    is_reversal=True,
                    supersedes_event_id=k.event_id,
                    template_id="reversal",
                )
            )

    n_irrelevant = round(config.irrelevant_note_rate * max(len(evidence_rows), 1))
    entity_keys = sorted({k.entity_key for k in knowables})
    horizon_start = datetime.combine(config.start_date, datetime.min.time())
    horizon_end = horizon_start + timedelta(weeks=config.n_weeks)
    horizon_days = max((horizon_end - horizon_start).days, 1)

    for _ in range(n_irrelevant):
        authored_at = horizon_start + timedelta(days=rng.randint(0, horizon_days - 1))
        available_at = _sample_available_at(authored_at, config, rng)
        source_id = _new_source_id()
        text = templates.render_irrelevant_note(rng)

        evidence_rows.append(
            SourceEvidence(
                source_id=source_id,
                source_type=rng.choice(_SOURCE_TYPES),
                source_record_id=source_id,
                source_revision="r1",
                authored_at=authored_at,
                available_at=available_at,
                raw_text=text,
                content_hash=_content_hash(text),
                entity_mentions_raw=[rng.choice(entity_keys)] if entity_keys else [],
            )
        )
        ground_truth_rows.append(
            NoteGroundTruth(
                source_id=source_id,
                event_id=None,
                signal_type=SignalType.NO_SIGNAL,
                direction=Direction.NA,
                business_certainty=BusinessCertainty.UNKNOWN,
                conditionality=Conditionality.NONE,
                condition_text=None,
                stated_magnitude_value=None,
                stated_magnitude_unit=None,
                effective_start=None,
                effective_end=None,
                negated=False,
                is_irrelevant=True,
                is_reversal=False,
                supersedes_event_id=None,
                template_id="irrelevant",
            )
        )

    return evidence_rows, ground_truth_rows
