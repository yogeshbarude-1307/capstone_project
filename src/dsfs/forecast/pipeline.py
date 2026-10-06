"""CLI entry point for the 4-arm forecast experiment (Milestones 7-8).

Runs all four arms under identical config and produces a results report.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from dsfs.config import Settings, get_settings
from dsfs.evaluation.ablation import ABLATIONS, NOT_IMPLEMENTED, run_ablation_matrix
from dsfs.evaluation.segments import per_horizon, signal_exposed_subset
from dsfs.evaluation.paired import trajectory_lift_ci
from dsfs.features.access import load_feature_store
from dsfs.forecast.harness import (
    DEFAULT_HORIZON_WEEKS,
    DEFAULT_TRAIN_WEEKS,
    ArmResult,
    ExperimentMetrics,
    ForecastConfig,
    compute_mae,
    evaluate_arm,
    run_arm,
    paired_origins,
)
from dsfs.forecast.oracle import build_oracle_features
from dsfs.forecast.shuffle import shuffle_features
from dsfs.synth.config import GeneratorConfig
from dsfs.synth.entities import generate_entities

POC_CAVEAT = (
    "This synthetic POC evaluates whether early qualitative signals improve forecasts. "
    "Positive forecast value is established only when the reported comparison supports it. "
    "It does **not** demonstrate that "
    "real company account/service/supplier notes contain comparable predictive "
    "information, at what prevalence, or with what real lead time. Real-data "
    "validation is a required, separate, subsequent gate before any production "
    "claim is made."
)


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


@dataclass
class ExperimentData:
    """Everything the ablation matrix needs to re-run arms B/C under masked
    feature sets, without recomputing D0/oracle/extraction from scratch."""
    d0: pd.DataFrame
    config: ForecastConfig
    metrics: dict[str, ExperimentMetrics]
    arm_results: dict[str, ArmResult]
    oracle_features: pd.DataFrame
    extracted_features: pd.DataFrame
    http_request_count: int = 0


def run_experiment(
    settings: Settings,
    extraction_run_id: str,
    forecast_config: ForecastConfig | None = None,
) -> ExperimentData:
    """Run the full 4-arm experiment and return metrics + arm results per arm."""
    config = forecast_config or ForecastConfig()
    d0 = _load_d0(settings)
    gen_config = _load_config(settings)
    entities = generate_entities(gen_config)
    cutoffs = _cutoffs_from_d0(d0)

    arm_a = run_arm(d0, config, "A", signal_features=None)
    metrics_a = evaluate_arm(arm_a)

    gt_path = settings.data_raw_dir / "d1_note_ground_truth.jsonl"
    notes_path = settings.data_raw_dir / "d1_notes.jsonl"
    from dsfs.models.source_evidence import SourceEvidence
    from dsfs.models.signal_record import SignalRecord
    from dsfs.synth.notes import NoteGroundTruth
    from dsfs.extraction.ledger import read_ledger
    from dsfs.forecast.oracle_service import oracle_service
    from dsfs.features.service import DemandFeatureService
    sources = {s.source_id:s for s in [SourceEvidence.model_validate_json(line) for line in notes_path.read_text(encoding="utf-8").splitlines() if line]}
    truth = [NoteGroundTruth.model_validate_json(line) for line in gt_path.read_text(encoding="utf-8").splitlines() if line]
    signals = [SignalRecord.model_validate(r) for r in read_ledger(settings.data_processed_dir / "signal_ledger.jsonl")
               if r["extraction_run_id"] == extraction_run_id]
    delays_path = settings.data_processed_dir / "publication_delays.json"
    delays = json.loads(delays_path.read_text()) if delays_path.exists() else {}
    pairs = [(e,c) for c in cutoffs for e in entities]
    oracle_features = oracle_service(d0, truth, sources, extraction_run_id, delays=delays, forecast_config=config).historical(pairs, range(1,config.horizon_weeks+1))
    arm_b = run_arm(d0, config, "B", signal_features=oracle_features)

    service = DemandFeatureService(d0, signals, sources, extraction_run_id, delays=delays, forecast_config=config)
    from dsfs.features.providers import serve_local
    with serve_local(service) as provider:
        extracted_features = provider.retrieve(pairs, range(1, config.horizon_weeks+1))
        http_request_count = provider.request_count
    arm_c = run_arm(d0, config, "C", signal_features=extracted_features)

    arm_results = {"A": arm_a, "B": arm_b, "C": arm_c}
    if len(entities) > 1:
        shuffled_features = shuffle_features(extracted_features)
        # Tabular history stays attached to the correct account in the control.
        shuffled_features = shuffled_features.drop(columns=["tabular_features"])
        arm_results["D"] = run_arm(d0, config, "D", signal_features=shuffled_features)
    for result in arm_results.values():
        paired_origins(arm_a, result)
    metrics = {
        label: evaluate_arm(result, baseline_mae=metrics_a.mae)
        for label, result in arm_results.items()
    }

    return ExperimentData(
        d0=d0, config=config, metrics=metrics, arm_results=arm_results,
        oracle_features=oracle_features, extracted_features=extracted_features,
        http_request_count=http_request_count,
    )


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
        "| Arm | Description | MASE | MAE | Bias | Origins | MAE lift vs A |",
        "|-----|-------------|------|-----|------|---------|-----------|",
    ]

    descriptions = {
        "A": "Tabular only (baseline)",
        "B": "Oracle (ground truth)",
        "C": "Extracted signals",
        "D": "Shuffled control",
    }

    for arm_label in ["A", "B", "C", "D"]:
        if arm_label not in results:
            lines.append(f"| {arm_label} | Unavailable (single account) | — | — | — | 0 | — |")
            continue
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
    d_mae = results["D"].mae if "D" in results else a_mae

    b_lift = (a_mae - b_mae) / a_mae if a_mae > 0 else 0
    c_lift = (a_mae - c_mae) / a_mae if a_mae > 0 else 0
    d_lift = (a_mae - d_mae) / a_mae if a_mae > 0 else 0

    lines.append("Point estimates alone do not establish forecast value. The run manifest reports paired MASE lift and 95% account-trajectory confidence intervals; the frozen multi-seed study determines the oracle gate.")
    if b_lift <= 0:
        lines.append("Oracle MAE does not improve on baseline in this run. Revisit representation before expanding extraction technology.")
    elif c_lift <= 0:
        lines.append("Oracle MAE improves, but extracted MAE does not. Check interpretation and representation after the frozen oracle gate.")
    else:
        lines.append("Both oracle and extracted MAE improve in this run; assess their paired uncertainty before drawing conclusions.")
    if d_lift > 0:
        lines.append("The shuffled control also improves on baseline. This can reflect common signal structure or chance; inspect its paired uncertainty and temporal regression checks.")

    lines.extend([
        "",
        "## Mandatory Reporting Caveat",
        "",
        "> " + POC_CAVEAT,
    ])

    return "\n".join(lines)


def _format_ablation_report(data: ExperimentData) -> str:
    """M9 ablation matrix (docs/08): which representation of the qualitative
    signal actually carries the lift, for arms B (oracle) and C (extracted).
    """
    a_mae = data.metrics["A"].mae
    a_errors = np.abs(data.arm_results["A"].actuals - data.arm_results["A"].predictions)

    lines = [
        "# Forecast Ablation Matrix (Milestone 9)",
        "",
        "Each row keeps only the listed feature columns; every other signal "
        "column is removed before merging, so the model sees strictly less "
        "information as you go up the table. Lift and its 95% CI are computed "
        "by resampling complete paired account trajectories against arm A (MAE).",
        "",
    ]

    for arm_label in ("B", "C"):
        signal_features = data.oracle_features if arm_label == "B" else data.extracted_features
        results = run_ablation_matrix(
            data.d0, data.config, signal_features, arm_label=arm_label, baseline_result=data.arm_results["A"],
            full_result=data.arm_results[arm_label],
        )
        # The "full" ablation applies no masking, so it is identical by
        # construction to the already-computed top-level arm result — reuse
        # it instead of re-running the harness for the same numbers twice.
        results["full"] = data.arm_results[arm_label]
        lines.extend([
            f"## Arm {arm_label} ({'oracle' if arm_label == 'B' else 'extracted'})",
            "",
            "| Ablation | MAE | Lift vs A | Lift 95% CI | Origins |",
            "|---|---:|---:|---:|---:|",
        ])
        for name in ABLATIONS:
            arm_result = results[name]
            if len(arm_result.origins) == 0:
                lines.append(f"| {name} | — | — | — | 0 |")
                continue
            errors = np.abs(arm_result.actuals - arm_result.predictions)
            mae = float(errors.mean())
            uncertainty = trajectory_lift_ci(data.arm_results["A"], arm_result, metric="mae", seed=data.config.random_state)
            point, lo, hi = (uncertainty[k] for k in ("point", "ci_low", "ci_high"))
            lines.append(
                f"| {name} | {mae:.2f} | {point:+.2%} | [{lo:+.2%}, {hi:+.2%}] | {len(arm_result.origins)} |"
            )
        lines.append("")

    lines.extend(["## Not implemented in this POC", ""])
    for name, reason in NOT_IMPLEMENTED.items():
        lines.append(f"- **{name}**: {reason}")
    lines.append("")

    lines.extend([
        "## Segment breakdowns (arm C, full ablation)",
        "",
    ])
    # Identical to the "full" row already reported above for arm C.
    full_c = data.arm_results["C"]
    horizons = per_horizon(full_c.origins)
    if horizons:
        lines.extend(["| Horizon (weeks) | MAE | Origins |", "|---:|---:|---:|"])
        for h, origins in horizons.items():
            errs = np.abs(np.array([o.actual for o in origins]) - np.array([o.predicted for o in origins]))
            lines.append(f"| {h} | {errs.mean():.2f} | {len(origins)} |")
        lines.append("")
    else:
        lines.append("No origins produced for arm C at this scale/config.")
        lines.append("")

    exposed = signal_exposed_subset(full_c.origins, data.extracted_features)
    lines.extend([
        f"Signal-exposed subset (origins where arm C had an active signal at cutoff): "
        f"**{len(exposed)} / {len(full_c.origins)}** origins.",
        "",
        "Per-generator-segment (product family / customer tier), entity-resolved-only, "
        "and early-signal subsets are not computed here — the generator defines no "
        "such segment, and threading entity-resolution/lead-time status through to "
        "forecast origins is follow-up scope (docs/16-revised-execution-plan.md).",
        "",
        "## Mandatory Reporting Caveat",
        "",
        "> " + POC_CAVEAT,
    ])
    return "\n".join(lines)


def main(settings: Settings | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run 4-arm forecast experiment (Milestones 7-8)")
    parser.add_argument("--run-id", required=True, help="Extraction run ID for arm C features")
    parser.add_argument("--train-weeks", type=int, default=DEFAULT_TRAIN_WEEKS)
    parser.add_argument("--horizon-weeks", type=int, default=DEFAULT_HORIZON_WEEKS)
    parser.add_argument(
        "--ablation", choices=("none", "full"), default="none",
        help="Also run the M9 ablation matrix (docs/08) for arms B and C.",
    )
    args = parser.parse_args()

    settings = settings or get_settings()
    settings.ensure_dirs()

    config = ForecastConfig(
        train_weeks=args.train_weeks,
        horizon_weeks=args.horizon_weeks,
    )

    data = run_experiment(settings, args.run_id, config)

    report = _format_report(data.metrics, config)
    report_dir = settings.reports_dir / "forecast"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "experiment_results.md"
    report_path.write_text(report, encoding="utf-8")

    print(report)
    print(f"\nReport written to: {report_path}")

    if args.ablation == "full":
        ablation_report = _format_ablation_report(data)
        ablation_path = report_dir / "forecast_ablation_results.md"
        ablation_path.write_text(ablation_report, encoding="utf-8")
        print(f"\nAblation matrix written to: {ablation_path}")


if __name__ == "__main__":
    main()
