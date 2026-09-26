"""CLI entry point for the 4-arm forecast experiment (Milestones 7-8).

Runs all four arms under identical config and produces a results report.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from dsfs.config import Settings, get_settings
from dsfs.features.access import load_feature_store
from dsfs.forecast.harness import (
    DEFAULT_HORIZON_WEEKS,
    DEFAULT_TRAIN_WEEKS,
    ArmResult,
    ExperimentMetrics,
    ForecastConfig,
    evaluate_arm,
    run_arm,
)
from dsfs.forecast.oracle import build_oracle_features
from dsfs.forecast.shuffle import shuffle_features
from dsfs.synth.config import GeneratorConfig
from dsfs.synth.entities import generate_entities


def _load_d0(settings: Settings) -> pd.DataFrame:
    path = settings.data_raw_dir / "d0_tabular_demand.parquet"
    if not path.exists():
        raise FileNotFoundError(f"D0 not found: {path}. Run dsfs-generate first.")
    return pd.read_parquet(path)


def _load_config(settings: Settings) -> GeneratorConfig:
    path = settings.data_raw_dir / "generator_config.json"
    return GeneratorConfig.model_validate(json.loads(path.read_text(encoding="utf-8")))


def _cutoffs_from_d0(d0: pd.DataFrame) -> list[datetime]:
    dates = sorted(d0["period_start"].unique())
    return [
        pd.Timestamp(d).to_pydatetime().replace(tzinfo=timezone.utc)
        for d in dates
    ]


def run_experiment(
    settings: Settings,
    extraction_run_id: str,
    forecast_config: ForecastConfig | None = None,
) -> dict[str, ExperimentMetrics]:
    """Run the full 4-arm experiment and return metrics per arm."""
    config = forecast_config or ForecastConfig()
    d0 = _load_d0(settings)
    gen_config = _load_config(settings)
    entities = generate_entities(gen_config)
    cutoffs = _cutoffs_from_d0(d0)

    arm_a = run_arm(d0, config, "A", signal_features=None)
    metrics_a = evaluate_arm(arm_a)

    gt_path = settings.data_raw_dir / "d1_note_ground_truth.jsonl"
    notes_path = settings.data_raw_dir / "d1_notes.jsonl"
    oracle_features = build_oracle_features(
        gt_path, notes_path, cutoffs, entities,
    )
    arm_b = run_arm(d0, config, "B", signal_features=oracle_features)

    store = load_feature_store(
        settings.data_processed_dir / "signal_ledger.jsonl",
        notes_path,
        extraction_run_id=extraction_run_id,
    )
    entity_cutoff_pairs = [(e, c) for c in cutoffs for e in entities]
    extracted_features = store.get_historical_features(entity_cutoff_pairs)
    arm_c = run_arm(d0, config, "C", signal_features=extracted_features)

    shuffled_features = shuffle_features(extracted_features)
    arm_d = run_arm(d0, config, "D", signal_features=shuffled_features)

    results = {}
    for arm_result in [arm_a, arm_b, arm_c, arm_d]:
        m = evaluate_arm(arm_result, baseline_mae=metrics_a.mae)
        results[arm_result.arm] = m

    return results


def _format_report(results: dict[str, ExperimentMetrics], config: ForecastConfig) -> str:
    lines = [
        "# Forecast Experiment Results (Milestones 7-8)",
        "",
        "## Configuration",
        f"- Training window: {config.train_weeks} weeks",
        f"- Forecast horizon: {config.horizon_weeks} weeks",
        f"- Ridge alpha: {config.ridge_alpha}",
        f"- Lag features: {config.lag_weeks}",
        f"- Random state: {config.random_state}",
        "",
        "## Results",
        "",
        "| Arm | Description | MASE | MAE | Bias | Origins | Lift vs A |",
        "|-----|-------------|------|-----|------|---------|-----------|",
    ]

    descriptions = {
        "A": "Tabular only (baseline)",
        "B": "Oracle (ground truth)",
        "C": "Extracted signals",
        "D": "Shuffled control",
    }

    for arm_label in ["A", "B", "C", "D"]:
        m = results[arm_label]
        lift = f"{m.incremental_lift_vs_a:+.4f}" if m.incremental_lift_vs_a is not None else "—"
        lines.append(
            f"| {arm_label} | {descriptions[arm_label]} | "
            f"{m.mase:.4f} | {m.mae:.2f} | {m.bias:+.2f} | "
            f"{m.n_origins} | {lift} |"
        )

    lines.extend([
        "",
        "## Decision Logic (docs/08)",
        "",
    ])

    a_mae = results["A"].mae
    b_mae = results["B"].mae
    c_mae = results["C"].mae
    d_mae = results["D"].mae

    b_lift = (a_mae - b_mae) / a_mae if a_mae > 0 else 0
    c_lift = (a_mae - c_mae) / a_mae if a_mae > 0 else 0
    d_lift = (a_mae - d_mae) / a_mae if a_mae > 0 else 0

    if d_lift > 0.02:
        lines.append("**WARNING:** Arm D shows meaningful lift — investigate leakage.")
    elif b_lift < 0.01:
        lines.append("B ~ A: the planted signal itself carries no forecastable information.")
    elif c_lift < 0.005:
        lines.append("B > A but C ~ A: oracle signal is useful but extraction is the bottleneck.")
    else:
        frac = c_lift / b_lift if b_lift > 0 else 0
        lines.append(f"C retains {frac:.1%} of oracle lift. End-to-end mechanics work.")

    lines.extend([
        "",
        "## Mandatory Reporting Caveat",
        "",
        "> This POC demonstrates that a deliberately planted, causally-consistent early "
        "signal can be recovered from synthetic notes and shown to add measurable value "
        "to a forecast under controlled conditions. It does **not** demonstrate that "
        "real company account/service/supplier notes contain comparable predictive "
        "information, at what prevalence, or with what real lead time. Real-data "
        "validation is a required, separate, subsequent gate before any production "
        "claim is made.",
    ])

    return "\n".join(lines)


def main(settings: Settings | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run 4-arm forecast experiment (Milestones 7-8)")
    parser.add_argument("--run-id", required=True, help="Extraction run ID for arm C features")
    parser.add_argument("--train-weeks", type=int, default=DEFAULT_TRAIN_WEEKS)
    parser.add_argument("--horizon-weeks", type=int, default=DEFAULT_HORIZON_WEEKS)
    args = parser.parse_args()

    settings = settings or get_settings()
    settings.ensure_dirs()

    config = ForecastConfig(
        train_weeks=args.train_weeks,
        horizon_weeks=args.horizon_weeks,
    )

    results = run_experiment(settings, args.run_id, config)

    report = _format_report(results, config)
    report_dir = settings.reports_dir / "forecast"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "experiment_results.md"
    report_path.write_text(report, encoding="utf-8")

    print(report)
    print(f"\nReport written to: {report_path}")


if __name__ == "__main__":
    main()
