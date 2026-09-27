"""Shared fixture: a real generate -> extract -> features run, for lineage/freshness tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from dsfs.config import Settings
from dsfs.extraction.pipeline import run_and_persist
from dsfs.features.pipeline import build_d3
from dsfs.synth.config import GeneratorConfig
from dsfs.synth.entities import generate_entities
from dsfs.synth.generator import generate_dataset, write_dataset


@pytest.fixture
def real_pipeline_run(tmp_path: Path):
    settings = Settings(
        data_raw_dir=tmp_path / "raw",
        data_interim_dir=tmp_path / "interim",
        data_processed_dir=tmp_path / "processed",
        reports_dir=tmp_path / "reports",
    )
    settings.ensure_dirs()

    config = GeneratorConfig(seed=4, n_entities=4, n_weeks=30)
    dataset = generate_dataset(config)
    write_dataset(dataset, settings.data_raw_dir)

    known_entities = set(generate_entities(config))
    ledger_path = settings.data_processed_dir / "signal_ledger.jsonl"
    result = run_and_persist(dataset.d1_notes, known_entities, ledger_path)

    d3_path, row_count, schema_failures = build_d3(settings, extraction_run_id=result.extraction_run_id)
    assert schema_failures == 0

    return {
        "settings": settings,
        "extraction_run_id": result.extraction_run_id,
        "d3_path": d3_path,
        "ledger_path": ledger_path,
        "notes_path": settings.data_raw_dir / "d1_notes.jsonl",
    }
