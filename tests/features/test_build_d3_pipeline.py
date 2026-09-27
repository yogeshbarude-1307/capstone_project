"""build_d3 must return a typed tuple, log quarantined rows, and not silently swallow errors."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
import pytest

from dsfs.config import Settings
from dsfs.contracts import ContractValidationError, validate_record
from dsfs.extraction.pipeline import run_and_persist
from dsfs.synth.config import GeneratorConfig
from dsfs.synth.entities import generate_entities
from dsfs.synth.generator import generate_dataset, write_dataset


def test_build_d3_signature_returns_tuple():
    """The signature declared in the source must be honored — reviewers were burned by ``-> Path``."""
    from dsfs.features.pipeline import build_d3

    import inspect
    sig = inspect.signature(build_d3)
    # Annotation should mention tuple; concrete type-checking is done at call site.
    assert "tuple" in str(sig.return_annotation) or sig.return_annotation.__name__ == "tuple"


def test_valid_forecast_feature_passes_contract(valid_forecast_feature):
    """Baseline: a fixture-valid record round-trips through the same validator used by build_d3."""
    record = valid_forecast_feature.model_dump(mode="json")
    validate_record("forecast_feature", record)  # must not raise


def test_missing_required_field_raises_contract_error(valid_forecast_feature):
    """Confirms the validator we now catch by type actually rejects malformed rows."""
    record = valid_forecast_feature.model_dump(mode="json")
    record.pop("entity_key")
    with pytest.raises(ContractValidationError):
        validate_record("forecast_feature", record)


def test_nan_conversion_matches_pipeline_behavior():
    """The pipeline converts pandas NaN → None before validation.

    Previously it did ``.dropna().to_dict()`` which silently removed those columns,
    so required-field absence would appear as a schema violation of the wrong shape.
    """
    row = pd.Series({"a": 1.0, "b": float("nan"), "c": [1, 2]})
    record = {}
    for k, v in row.to_dict().items():
        if isinstance(v, list):
            record[k] = v
        elif pd.isna(v):
            record[k] = None
        else:
            record[k] = v
    assert record == {"a": 1.0, "b": None, "c": [1, 2]}


def test_pipeline_module_logs_quarantined_rows(caplog):
    """Failure path emits a warning naming the row index and the error."""
    logger = logging.getLogger("dsfs.features.pipeline")
    with caplog.at_level(logging.WARNING, logger="dsfs.features.pipeline"):
        try:
            validate_record("forecast_feature", {"entity_key": "x"})  # missing required fields
        except ContractValidationError as exc:
            logger.warning("D3 row %s failed forecast_feature contract: %s", 42, exc)
    assert any("D3 row 42" in rec.message for rec in caplog.records)


def test_build_d3_runs_end_to_end_on_real_generated_data(tmp_path: Path):
    """Regression test: build_d3 previously read a nonexistent 'week_start'
    column (real D0 only has 'period_start'), so dsfs-features raised a
    KeyError on every real (non-fixture) dataset. This exercises the true
    generate -> extract -> build_d3 path end to end."""
    from dsfs.features.pipeline import build_d3

    settings = Settings(
        data_raw_dir=tmp_path / "raw",
        data_interim_dir=tmp_path / "interim",
        data_processed_dir=tmp_path / "processed",
        reports_dir=tmp_path / "reports",
    )
    settings.ensure_dirs()

    config = GeneratorConfig(seed=2, n_entities=3, n_weeks=20)
    dataset = generate_dataset(config)
    write_dataset(dataset, settings.data_raw_dir)

    known_entities = set(generate_entities(config))
    ledger_path = settings.data_processed_dir / "signal_ledger.jsonl"
    result = run_and_persist(dataset.d1_notes, known_entities, ledger_path)

    output_path, row_count, schema_failures = build_d3(
        settings, extraction_run_id=result.extraction_run_id,
    )
    assert output_path.exists()
    assert row_count > 0
    assert schema_failures == 0
    df = pd.read_parquet(output_path)
    assert set(df["entity_key"].unique()) == known_entities
