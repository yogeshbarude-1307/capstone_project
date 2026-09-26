"""Runs the extractor over a note corpus, validates every output against the
canonical signal_record contract (docs/04-api-data-contracts.md — a record
that fails validation is quarantined, never silently coerced or dropped),
and appends accepted records to the local, append-only signal ledger.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from dsfs.config import Settings, get_settings
from dsfs.contracts import ContractValidationError, validate_record
from dsfs.extraction.extractor import (
    DEFAULT_EXTRACTION_CONFIG_VERSION,
    DEFAULT_EXTRACTOR_VERSION,
    extract_signal,
)
from dsfs.extraction.ledger import append_to_ledger
from dsfs.extraction.reconciliation import reconcile_reversal
from dsfs.models.signal_record import SignalRecord
from dsfs.models.source_evidence import SourceEvidence
from dsfs.synth.config import GeneratorConfig
from dsfs.synth.entities import generate_entities


@dataclass
class QuarantinedRecord:
    source_id: str
    error: str
    stage: str  # "construct" (pydantic model construction) or "contract" (JSON Schema)
    source_evidence: dict
    extraction_run_id: str
    rejected_record: dict | None = None


@dataclass
class ExtractionRunResult:
    extraction_run_id: str
    accepted: list[SignalRecord] = field(default_factory=list)
    quarantined: list[QuarantinedRecord] = field(default_factory=list)

    @property
    def schema_conformance_rate(self) -> float:
        total = len(self.accepted) + len(self.quarantined)
        return 1.0 if total == 0 else len(self.accepted) / total


def new_extraction_run_id() -> str:
    return f"run-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}"


def run_extraction(
    notes: list[SourceEvidence],
    known_entities: set[str],
    *,
    extraction_run_id: str | None = None,
    extractor_version: str = DEFAULT_EXTRACTOR_VERSION,
    extraction_config_version: str = DEFAULT_EXTRACTION_CONFIG_VERSION,
    extracted_at: datetime | None = None,
) -> ExtractionRunResult:
    run_id = extraction_run_id or new_extraction_run_id()
    result = ExtractionRunResult(extraction_run_id=run_id)
    run_time = extracted_at or datetime.now(timezone.utc)
    sources = {note.source_id: note for note in notes}
    if len(sources) != len(notes):
        raise ValueError("Source IDs must be unique within an extraction snapshot")

    for evidence in sorted(notes, key=lambda n: (n.available_at, n.source_id)):
        try:
            record = extract_signal(
                evidence,
                known_entities,
                extraction_run_id=run_id,
                extractor_version=extractor_version,
                extraction_config_version=extraction_config_version,
                extracted_at=run_time,
            )
            record = reconcile_reversal(record, evidence, result.accepted, sources)
        except ValidationError as exc:
            result.quarantined.append(
                QuarantinedRecord(evidence.source_id, str(exc), "construct", evidence.model_dump(mode="json"), run_id)
            )
            continue

        dumped = record.model_dump(mode="json")
        try:
            validate_record("signal_record", dumped)
        except ContractValidationError as exc:
            result.quarantined.append(
                QuarantinedRecord(evidence.source_id, str(exc), "contract", evidence.model_dump(mode="json"), run_id, dumped)
            )
            continue

        result.accepted.append(record)

    return result


def run_and_persist(
    notes: list[SourceEvidence],
    known_entities: set[str],
    ledger_path: Path,
    **kwargs,
) -> ExtractionRunResult:
    result = run_extraction(notes, known_entities, **kwargs)
    append_to_ledger(result.accepted, ledger_path)
    if result.quarantined:
        rejected_path = ledger_path.with_name(ledger_path.stem + "_rejected.jsonl")
        with rejected_path.open("a", encoding="utf-8") as f:
            for rejected in result.quarantined:
                f.write(json.dumps(asdict(rejected)) + "\n")
    return result


def _load_notes(path: Path) -> list[SourceEvidence]:
    with path.open(encoding="utf-8") as f:
        return [SourceEvidence.model_validate_json(line) for line in f if line.strip()]


def main(settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    if settings.llm_extraction_enabled:
        raise NotImplementedError("Local LLM extraction is not implemented; disable it to use the explicit rules baseline.")
    settings.ensure_dirs()

    d1_notes_path = settings.data_raw_dir / "d1_notes.jsonl"
    generator_config_path = settings.data_raw_dir / "generator_config.json"
    if not d1_notes_path.exists() or not generator_config_path.exists():
        raise FileNotFoundError(
            f"Expected {d1_notes_path} and {generator_config_path} to exist. "
            "Run 'python -m dsfs.synth.generator' first (Milestone 2)."
        )

    notes = _load_notes(d1_notes_path)
    config = GeneratorConfig.model_validate(json.loads(generator_config_path.read_text(encoding="utf-8")))
    known_entities = set(generate_entities(config))

    ledger_path = settings.data_processed_dir / "signal_ledger.jsonl"
    result = run_and_persist(notes, known_entities, ledger_path)

    print("Extraction pipeline run (Milestone 3):")
    print(f"  extraction_run_id: {result.extraction_run_id}")
    print(f"  notes processed: {len(notes)}")
    print(f"  accepted: {len(result.accepted)}")
    print(f"  quarantined: {len(result.quarantined)}")
    print(f"  schema_conformance_rate: {result.schema_conformance_rate:.4f}")
    print(f"  ledger: {ledger_path}")


if __name__ == "__main__":
    main()
