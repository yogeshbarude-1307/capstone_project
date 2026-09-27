"""End-to-end orchestrator (docs/12 Milestone 11): chains the existing
per-stage CLIs' underlying functions on a fresh generation, producing every
artifact in one run without manual intervention.

    dsfs-run --config configs/e2e_smoke.json --output-dir reports/run_<ts>

Each step calls an existing, already-tested function — this module contains
no new pipeline logic of its own, only sequencing and a manifest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from dsfs.config import REPO_ROOT, Settings, get_settings
from dsfs.drift.monitors import monitor_note_length, monitor_source_type_mix
from dsfs.drift.report import ScenarioDriftResult, evaluate_scenario, render_report
from dsfs.evaluation.annotations import load_dataset
from dsfs.evaluation.metrics import MetricConfig
from dsfs.evaluation.report import code_snapshot, write_bundle
from dsfs.extraction.pipeline import run_and_persist
from dsfs.features.pipeline import build_d3
from dsfs.forecast.harness import ForecastConfig
from dsfs.forecast.pipeline import _format_ablation_report, _format_report, run_experiment
from dsfs.lineage import trace_sample
from dsfs.synth.config import GeneratorConfig
from dsfs.synth.entities import generate_entities
from dsfs.synth.generator import generate_dataset, write_dataset

DEFAULT_CONFIG = {
    "generator": {"seed": 1, "n_entities": 10, "n_weeks": 60},
    "forecast": {"train_weeks": 30, "horizon_weeks": 2, "ablation": "full"},
    "lineage_sample_size": 10,
    "evaluation_dataset": "data/annotations/d2_starter.json",
}

_SCENARIO_MONITORS = {
    "note_length_shift": monitor_note_length,
    "source_type_mix_shift": monitor_source_type_mix,
}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def load_run_config(path: Path | None) -> dict:
    if path is None:
        return DEFAULT_CONFIG
    return json.loads(path.read_text(encoding="utf-8"))


def run_e2e(settings: Settings, run_config: dict) -> dict:
    """Run every stage once and return a manifest dict. Raises on any stage
    failure — this is meant to surface integration problems, not mask them."""
    settings.ensure_dirs()
    manifest: dict = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "run_config": run_config,
        "code_sha256": code_snapshot(),
        "artifacts": {},
        "steps": {},
    }

    def _record(name: str, path: Path) -> None:
        try:
            rel = path.relative_to(REPO_ROOT)
        except ValueError:
            rel = path
        manifest["artifacts"][name] = {
            "path": str(rel),
            "sha256": _sha256_file(path) if path.is_file() else None,
        }

    # 1. synth
    gen_config = GeneratorConfig(**run_config.get("generator", {}))
    dataset = generate_dataset(gen_config)
    paths = write_dataset(dataset, settings.data_raw_dir)
    for name, path in paths.items():
        _record(name, path)
    manifest["steps"]["synth"] = dataset.summary()

    # 2. extraction
    known_entities = set(generate_entities(gen_config))
    ledger_path = settings.data_processed_dir / "signal_ledger.jsonl"
    extraction_result = run_and_persist(dataset.d1_notes, known_entities, ledger_path)
    _record("signal_ledger", ledger_path)
    manifest["steps"]["extraction"] = {
        "extraction_run_id": extraction_result.extraction_run_id,
        "accepted": len(extraction_result.accepted),
        "quarantined": len(extraction_result.quarantined),
    }

    # 3. evaluation (fixed D2 dataset, independent of this run's generated corpus)
    eval_dataset_path = REPO_ROOT / run_config.get("evaluation_dataset", DEFAULT_CONFIG["evaluation_dataset"])
    eval_dataset = load_dataset(eval_dataset_path)
    eval_output_dir = settings.reports_dir / "extraction"
    eval_bundle_dir = write_bundle(eval_dataset, eval_output_dir, split="dev", config=MetricConfig())
    _record("extraction_evaluation_report", eval_bundle_dir / "report.md")
    manifest["steps"]["evaluation"] = {"bundle_dir": str(eval_bundle_dir)}

    # 4. features
    d3_path, row_count, schema_failures = build_d3(settings, extraction_run_id=extraction_result.extraction_run_id)
    _record("d3_features", d3_path)
    manifest["steps"]["features"] = {"row_count": row_count, "schema_failures": schema_failures}
    if schema_failures > 0:
        raise RuntimeError(f"D3 build produced {schema_failures} schema failures — aborting run")

    # 5. forecast (+ ablation matrix)
    forecast_cfg = run_config.get("forecast", {})
    fc = ForecastConfig(
        train_weeks=forecast_cfg.get("train_weeks", 30),
        horizon_weeks=forecast_cfg.get("horizon_weeks", 2),
        min_origins=forecast_cfg.get("min_origins", 10),
    )
    experiment_data = run_experiment(settings, extraction_result.extraction_run_id, fc)
    report_dir = settings.reports_dir / "forecast"
    report_dir.mkdir(parents=True, exist_ok=True)
    forecast_report_path = report_dir / "experiment_results.md"
    forecast_report_path.write_text(_format_report(experiment_data.metrics, fc), encoding="utf-8")
    _record("forecast_report", forecast_report_path)
    manifest["steps"]["forecast"] = {
        arm: {"mae": m.mae, "mase": m.mase, "lift_vs_a": m.incremental_lift_vs_a}
        for arm, m in experiment_data.metrics.items()
    }
    if forecast_cfg.get("ablation", "none") == "full":
        ablation_path = report_dir / "forecast_ablation_results.md"
        ablation_path.write_text(_format_ablation_report(experiment_data), encoding="utf-8")
        _record("forecast_ablation_report", ablation_path)

    # 6. drift (only if this run seeded a scenario this POC has a monitor for)
    drift_report_path = report_dir.parent / "drift" / "drift_results.md"
    drift_report_path.parent.mkdir(parents=True, exist_ok=True)
    monitor_fn = _SCENARIO_MONITORS.get(gen_config.drift_scenario)
    if gen_config.drift_scenario != "none" and monitor_fn is not None:
        scenario_result = evaluate_scenario(dataset.d1_notes, gen_config, monitor_fn)
        drift_report_path.write_text(render_report([scenario_result]), encoding="utf-8")
        manifest["steps"]["drift"] = asdict(scenario_result)
    else:
        note = (
            f"drift_scenario={gen_config.drift_scenario!r}: "
            + ("no seeded scenario for this run." if gen_config.drift_scenario == "none"
               else "no dedicated monitor implemented for this scenario in this POC (docs/10 stretch item).")
        )
        drift_report_path.write_text(f"# Drift Detection Report (Milestone 10)\n\n{note}\n", encoding="utf-8")
        manifest["steps"]["drift"] = {"skipped": True, "reason": note}
    _record("drift_report", drift_report_path)

    # 7. lineage sample
    lineage_traces = trace_sample(
        d3_path, ledger_path, settings.data_raw_dir / "d1_notes.jsonl",
        extraction_run_id=extraction_result.extraction_run_id,
        n=run_config.get("lineage_sample_size", 10),
    )
    manifest["steps"]["lineage"] = {
        "n_traced": len(lineage_traces),
        "n_complete": sum(t.is_complete for t in lineage_traces),
    }

    manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
    return manifest


def main(settings: Settings | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=None, help="JSON run config; defaults to a small smoke config")
    parser.add_argument("--output-dir", type=Path, default=None, help="Overrides Settings.reports_dir for this run")
    args = parser.parse_args()

    run_config = load_run_config(args.config)
    settings = settings or get_settings()
    if args.output_dir is not None:
        settings = settings.model_copy(update={"reports_dir": args.output_dir})

    manifest = run_e2e(settings, run_config)
    manifest_path = settings.reports_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")

    print("End-to-end run complete (Milestone 11):")
    for step, info in manifest["steps"].items():
        print(f"  {step}: {info}")
    print(f"Manifest written to: {manifest_path}")


if __name__ == "__main__":
    main()
