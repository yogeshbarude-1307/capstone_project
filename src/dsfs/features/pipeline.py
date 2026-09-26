"""CLI entry point for D3 feature dataset generation (Milestone 5).

Reads the signal ledger and D1 notes, builds PIT-correct feature rows for
every (entity, weekly cutoff) pair from the D0 demand history, validates
each row against the forecast_feature contract, and writes D3 as Parquet.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from dsfs.config import Settings, get_settings
from dsfs.contracts import validate_record
from dsfs.features.access import load_feature_store
from dsfs.features.transformer import DEFAULT_FEATURE_DEFINITION_VERSION
from dsfs.synth.config import GeneratorConfig
from dsfs.synth.entities import generate_entities


def _weekly_cutoffs(start: datetime, n_weeks: int) -> list[datetime]:
    """Generate Monday-aligned UTC cutoffs."""
    return [start + timedelta(weeks=w) for w in range(n_weeks)]


def build_d3(
    settings: Settings,
    *,
    extraction_run_id: str,
    feature_definition_version: str = DEFAULT_FEATURE_DEFINITION_VERSION,
) -> Path:
    """Build the D3 feature dataset and write it as Parquet.

    Returns the output path.
    """
    ledger_path = settings.data_processed_dir / "signal_ledger.jsonl"
    notes_path = settings.data_raw_dir / "d1_notes.jsonl"
    config_path = settings.data_raw_dir / "generator_config.json"
    d0_path = settings.data_raw_dir / "d0_tabular_demand.parquet"

    for p in (ledger_path, notes_path, config_path, d0_path):
        if not p.exists():
            raise FileNotFoundError(f"Required file missing: {p}")

    config = GeneratorConfig.model_validate(
        json.loads(config_path.read_text(encoding="utf-8"))
    )
    entities = generate_entities(config)

    d0 = pd.read_parquet(d0_path)
    cutoff_dates = sorted(d0["week_start"].unique())
    cutoffs = [pd.Timestamp(c).to_pydatetime().replace(tzinfo=timezone.utc) for c in cutoff_dates]

    store = load_feature_store(
        ledger_path,
        notes_path,
        extraction_run_id=extraction_run_id,
        feature_definition_version=feature_definition_version,
    )

    pairs = [(ek, c) for c in cutoffs for ek in entities]
    df = store.get_historical_features(pairs, feature_set_version=feature_definition_version)

    schema_failures = 0
    for _, row in df.iterrows():
        record = row.dropna().to_dict()
        record["contributing_signal_ids"] = list(record.get("contributing_signal_ids", []))
        try:
            validate_record("forecast_feature", record)
        except Exception:
            schema_failures += 1

    output_path = settings.data_processed_dir / "d3_features.parquet"
    settings.data_processed_dir.mkdir(parents=True, exist_ok=True)
    df.to_parquet(output_path, index=False)
    return output_path, len(df), schema_failures


def main(settings: Settings | None = None) -> None:
    parser = argparse.ArgumentParser(description="Build D3 feature dataset (Milestone 5)")
    parser.add_argument("--run-id", required=True, help="Extraction run ID to build features from")
    parser.add_argument(
        "--fdv",
        default=DEFAULT_FEATURE_DEFINITION_VERSION,
        help="Feature definition version",
    )
    args = parser.parse_args()

    settings = settings or get_settings()
    settings.ensure_dirs()

    output_path, total, failures = build_d3(
        settings,
        extraction_run_id=args.run_id,
        feature_definition_version=args.fdv,
    )

    print("Feature pipeline run (Milestone 5):")
    print(f"  extraction_run_id: {args.run_id}")
    print(f"  feature_definition_version: {args.fdv}")
    print(f"  feature rows: {total}")
    print(f"  schema failures: {failures}")
    print(f"  output: {output_path}")


if __name__ == "__main__":
    main()
