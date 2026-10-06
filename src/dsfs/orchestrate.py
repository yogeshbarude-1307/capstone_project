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
import math
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


def _run_stages(settings: Settings, run_config: dict, run_id: str) -> dict:
    """Run every stage once and return a manifest dict. Raises on any stage
    failure — this is meant to surface integration problems, not mask them."""
    settings.ensure_dirs()
    manifest: dict = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "run_config": run_config,
        "code_sha256": code_snapshot(),
        "artifacts": {},
        "steps": {},
        "run_id": run_id,
        "feature_schema_version": "1.0.0",
        "feature_definition_version": "demand-v1",
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

    if run_config.get("mechanics_check"):
        from dsfs.evaluation.mechanics import run_mechanics_scenario
        from dsfs.runs import atomic_json
        mechanics = run_mechanics_scenario()
        atomic_json(settings.reports_dir/"mechanics.json",mechanics)
        manifest["steps"]["mechanics"] = mechanics
        _record("mechanics_check",settings.reports_dir/"mechanics.json")
        if not mechanics["oracle_usable"]: raise RuntimeError("Small oracle mechanics gate failed")

    print(f"[{run_id}] Generate synthetic lifecycle and demand",flush=True)
    # 1. synth
    gen_config = GeneratorConfig(**run_config.get("generator", {}))
    dataset = generate_dataset(gen_config)
    paths = write_dataset(dataset, settings.data_raw_dir)
    for name, path in paths.items():
        _record(name, path)
    manifest["steps"]["synth"] = dataset.summary()

    print(f"[{run_id}] Extract and replay publication",flush=True)
    # 2. extraction
    known_entities = set(generate_entities(gen_config))
    ledger_path = settings.data_processed_dir / "signal_ledger.jsonl"
    extraction_result = run_and_persist(dataset.d1_notes, known_entities, ledger_path, extraction_run_id=run_id)
    _record("signal_ledger", ledger_path)
    manifest["steps"]["extraction"] = {
        "extraction_run_id": extraction_result.extraction_run_id,
        "accepted": len(extraction_result.accepted),
        "quarantined": len(extraction_result.quarantined),
        "schema_conformance_rate": extraction_result.schema_conformance_rate,
        "review_count": sum(s.validation_status.value == "REVIEW" for s in extraction_result.accepted),
    }
    from dsfs.features.publication import publication_summary
    sources = {s.source_id:s for s in dataset.d1_notes}
    delays = {}
    if run_config.get("inject_publication_delay") and sources:
        delays[sorted(sources)[0]] = 120
    (settings.data_processed_dir/"publication_delays.json").write_text(json.dumps(delays), encoding="utf-8")
    manifest["publication_delays"] = delays
    manifest["steps"]["freshness"] = publication_summary(sources, delays)
    # Separate injected breach demonstration so ordinary run metrics stay honest.
    manifest["steps"]["freshness"]["delayed_batch_demonstration"] = publication_summary(
        sources, {sorted(sources)[0]:120} if sources else {})
    forecast_cfg = dict(run_config.get("forecast", {}))
    ablation = forecast_cfg.pop("ablation", "none")
    fc = ForecastConfig(**forecast_cfg)
    manifest["forecast_config"] = asdict(fc)

    # 3. evaluation (fixed D2 dataset, independent of this run's generated corpus)
    eval_dataset_path = REPO_ROOT / run_config.get("evaluation_dataset", DEFAULT_CONFIG["evaluation_dataset"])
    eval_dataset = load_dataset(eval_dataset_path)
    eval_output_dir = settings.reports_dir / "extraction"
    eval_bundle_dir = write_bundle(eval_dataset, eval_output_dir, split="dev", config=MetricConfig())
    _record("extraction_evaluation_report", eval_bundle_dir / "report.md")
    manifest["steps"]["evaluation"] = {"bundle_dir": str(eval_bundle_dir)}

    # 4. features
    d3_path, row_count, schema_failures = build_d3(settings, extraction_run_id=extraction_result.extraction_run_id,
                                              horizons=tuple(range(1,fc.horizon_weeks+1)), forecast_config=fc)
    _record("d3_features", d3_path)
    manifest["steps"]["features"] = {"row_count": row_count, "schema_failures": schema_failures}
    if schema_failures > 0:
        raise RuntimeError(f"D3 build produced {schema_failures} schema failures — aborting run")

    print(f"[{run_id}] Forecast four paired arms over HTTP",flush=True)
    # 5. forecast (+ ablation matrix)
    experiment_data = run_experiment(settings, extraction_result.extraction_run_id, fc)
    report_dir = settings.reports_dir / "forecast"
    report_dir.mkdir(parents=True, exist_ok=True)
    forecast_report_path = report_dir / "experiment_results.md"
    forecast_report_path.write_text(_format_report(experiment_data.metrics, fc), encoding="utf-8")
    _record("forecast_report", forecast_report_path)
    manifest["steps"]["forecast"] = {
        arm: {"mae": m.mae, "mase": m.mase, "bias": m.bias, "n_origins": m.n_origins, "lift_vs_a": m.incremental_lift_vs_a,
              "mase_unavailable_count":m.mase_unavailable_count}
        for arm, m in experiment_data.metrics.items()
    }
    from dsfs.evaluation.paired import trajectory_lift_ci
    manifest["steps"]["serving"] = {"transport":"http", "request_count":experiment_data.http_request_count,
                                    "fallback":False}
    manifest["steps"]["forecast_uncertainty"] = {arm: trajectory_lift_ci(experiment_data.arm_results["A"], result)
                    for arm,result in experiment_data.arm_results.items() if arm != "A"}
    from dsfs.evaluation.segments import per_horizon, signal_exposed_subset
    from dsfs.forecast.harness import evaluate_arm, ArmResult
    segments = {}
    for arm,result in experiment_data.arm_results.items():
        groups = {f"horizon_{h}": rows for h,rows in per_horizon(result.origins).items()}
        features = experiment_data.oracle_features if arm == "B" else experiment_data.extracted_features
        exposed = signal_exposed_subset(result.origins, features)
        keys = {(o.entity_key,o.origin_week_index,o.horizon_step) for o in exposed}
        groups["signal_exposed"] = exposed
        groups["not_exposed"] = [o for o in result.origins if (o.entity_key,o.origin_week_index,o.horizon_step) not in keys]
        segments[arm] = {name: asdict(evaluate_arm(ArmResult(arm,result.config,rows))) if rows else
                        {"n_origins": 0, "mae": None, "mase": None, "bias": None} for name,rows in groups.items()}
    manifest["steps"]["forecast_segments"] = segments
    # Cache the interpretation matrices consumed by this experiment.
    for name,frame in (("oracle",experiment_data.oracle_features),("extracted_http",experiment_data.extracted_features)):
        matrix_path = report_dir / (name+"_features.parquet")
        frame.to_parquet(matrix_path,index=False)
        _record(name+"_matrix",matrix_path)
    origins_path = report_dir / "origins.json"
    from dsfs.runs import atomic_json
    atomic_json(origins_path, {arm:[asdict(o) for o in r.origins] for arm,r in experiment_data.arm_results.items()})
    _record("forecast_origins", origins_path)
    if ablation == "full":
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
    print(f"[{run_id}] Validate drift and lineage evidence",flush=True)
    if "writing_drift" in run_config and run_config["writing_drift"] is not False:
        from dsfs.drift.experiment import run_writing_change_experiment
        options = run_config["writing_drift"] if isinstance(run_config["writing_drift"], dict) else {}
        writing_report, writing_artifacts = run_writing_change_experiment(**options)
        writing_path = drift_report_path.with_name("writing_change.json")
        atomic_json(writing_path, writing_report)
        atomic_json(writing_path.with_name("matched_inputs.json"), writing_artifacts)
        _record("writing_drift_report", writing_path)
        _record("writing_drift_inputs", writing_path.with_name("matched_inputs.json"))
        manifest["steps"]["drift"] = writing_report
        drift_report_path.write_text("# Matched writing-change drift\n\n"
            f"Alert week: {writing_report['alert_week']}\n\nDegradation confirmation week: {writing_report['degradation_week']}\n\n"
            f"Warning lead time: {writing_report['lead_time_weeks']} weeks\n\n"
            f"No-drift false-alert rate: {writing_report['calibrated_false_alert_rate']} "
            f"({writing_report['n_no_drift_runs']} runs).\n", encoding="utf-8")
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
    lineage_report_path = report_dir.parent / "lineage" / "lineage_sample.md"
    lineage_report_path.parent.mkdir(parents=True, exist_ok=True)
    lineage_lines = ["# Lineage Sample (Milestone 10/11)", ""]
    for t in lineage_traces:
        lineage_lines.append(f"## {t.entity_key} @ {t.forecast_cutoff} "
                              f"({len(t.signals)}/{len(t.contributing_signal_ids)} signals resolved)")
        for s in t.signals:
            lineage_lines.append(f"- signal={s.signal_id} source={s.source_id} span={s.evidence_span!r}")
        lineage_lines.append("")
    lineage_report_path.write_text("\n".join(lineage_lines), encoding="utf-8")
    _record("lineage_sample", lineage_report_path)
    if run_config.get("prepare_review"):
        from dsfs.evaluation.review_package import prepare_review_package
        manifest["steps"]["independent_review"] = prepare_review_package(
            dataset.d1_notes, dataset.entities, settings.reports_dir/"review")
        _record("independent_review_instructions", settings.reports_dir/"review"/"REVIEW_INSTRUCTIONS.md")
        _record("independent_review_package", settings.reports_dir/"review"/"review_dataset.json")

    # Pin the evaluation input and all evaluation outputs, not just its Markdown.
    for path in sorted(eval_bundle_dir.rglob("*")):
        if path.is_file(): _record("evaluation/"+path.relative_to(eval_bundle_dir).as_posix(),path)
    _record("publication_schedule",settings.data_processed_dir/"publication_delays.json")

    # Include rejected records, configs and all supporting files in the bundle.
    root = settings.reports_dir.parent
    for path in sorted(root.rglob("*")):
        if path.is_file(): _record("snapshot/"+path.relative_to(root).as_posix(),path)

    manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
    return manifest


def run_e2e(settings: Settings, run_config: dict) -> dict:
    from dsfs.extraction.pipeline import new_extraction_run_id
    from dsfs.runs import pipeline_lock, run_settings, atomic_json
    from importlib.metadata import version
    import platform
    run_id = new_extraction_run_id()
    with pipeline_lock(settings):
        isolated = run_settings(settings, run_id)
        if isolated.reports_dir.parent.exists():
            raise RuntimeError("Run snapshot already exists")
        try:
            manifest = _run_stages(isolated, run_config, run_id)
            if manifest["code_sha256"] != code_snapshot():
                raise RuntimeError("Source or schemas changed during execution; run cannot be published")
            # JSON uses null for unavailable metrics, never NaN/Infinity.
            def clean(v):
                if isinstance(v, dict): return {k:clean(x) for k,x in v.items()}
                if isinstance(v, list): return [clean(x) for x in v]
                if isinstance(v, float) and not math.isfinite(v): return None
                return v
            manifest = clean(manifest)
            manifest["status"] = "complete"
            manifest["environment"] = {"python":platform.python_version(), "dependencies":{
                name:version(name) for name in ("numpy","pandas","pyarrow","pydantic","jsonschema","fastapi","uvicorn")}}
            manifest["snapshot_root"] = str(isolated.reports_dir.parent.resolve())
            atomic_json(isolated.reports_dir/"manifest.json", manifest)
            atomic_json(settings.reports_dir/"manifest.json", manifest)
            return manifest
        except Exception as exc:
            atomic_json(isolated.reports_dir/"failure.json", {"run_id":run_id,"status":"failed","error":str(exc)})
            raise


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

    print("End-to-end run complete (Milestone 11):")
    for step, info in manifest["steps"].items():
        print(f"  {step}: {info}")
    print(f"Manifest written to: {manifest_path}")


if __name__ == "__main__":
    main()
