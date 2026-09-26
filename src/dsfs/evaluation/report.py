"""Reproducible D2 runs and local JSON/Markdown report bundles."""

from __future__ import annotations

import hashlib
import json
import platform
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import timedelta
from importlib.metadata import version
from pathlib import Path

from dsfs.config import REPO_ROOT
from dsfs.evaluation.annotations import AnnotationDataset, AnnotatedCase, snapshot_hash, snapshot_payload
from dsfs.evaluation.metrics import MetricConfig, evaluate
from dsfs.extraction.extractor import DEFAULT_EXTRACTION_CONFIG_VERSION, DEFAULT_EXTRACTOR_VERSION
from dsfs.extraction.pipeline import run_extraction

EVALUATOR_VERSION = "extraction-eval-0.1.0"
POC_CAVEAT = (
    "This POC demonstrates that a deliberately planted, causally-consistent early signal can be recovered "
    "from synthetic notes and shown to add measurable value to a forecast under controlled conditions. "
    "It does **not** demonstrate that real company account/service/supplier notes contain comparable "
    "predictive information, at what prevalence, or with what real lead time. Real-data validation is "
    "a required, separate, subsequent gate before any production claim is made."
)


def code_snapshot() -> str:
    """Pin actual source/schema contents as well as declared version strings."""
    digest = hashlib.sha256()
    paths = list((REPO_ROOT / "src" / "dsfs").rglob("*.py"))
    paths += list((REPO_ROOT / "docs" / "schemas").glob("*.json"))
    for path in sorted(paths):
        digest.update(path.relative_to(REPO_ROOT).as_posix().encode("utf-8"))
        digest.update(path.read_text(encoding="utf-8").replace("\r\n", "\n").encode("utf-8"))
    return digest.hexdigest()


def label_status(case: AnnotatedCase) -> str:
    if case.label_origin == "assistant_draft" or case.adjudication_state == "draft":
        return "provisional"
    if case.adjudication_state in ("agreed", "resolved"):
        return "human_adjudicated"
    return "human_single"


def run_evaluation(
    dataset: AnnotationDataset,
    *,
    split: str = "dev",
    config: MetricConfig | None = None,
    require_gold: bool = False,
) -> tuple[dict, list, list]:
    """Run isolated scenarios; labels never enter the extractor interface."""
    if split not in ("dev", "test"):
        raise ValueError("Evaluation split must be dev or test")
    selected = [case for case in dataset.cases if case.split == split]
    if not selected:
        raise ValueError(f"No D2 cases in split {split!r}")
    statuses = Counter(label_status(c) for c in selected)
    if require_gold and (split != "test" or statuses["provisional"] or statuses["human_adjudicated"] / len(selected) < 0.2):
        raise ValueError("Gold mode requires a test split, human-reviewed labels, and >=20% double-adjudicated cases")
    config = config or MetricConfig()
    dataset_sha = snapshot_hash(dataset)
    code_sha = code_snapshot()
    run_payload = json.dumps([dataset_sha, code_sha, split, asdict(config)], sort_keys=True)
    run_id = "eval-" + hashlib.sha256(run_payload.encode("utf-8")).hexdigest()[:20]
    # Explicit simulated processing clock; this is reproducible offline replay.
    extracted_at = max(c.evidence.available_at for c in selected) + timedelta(seconds=1)
    scenarios = defaultdict(list)
    for case in selected:
        scenarios[case.scenario_id].append(case.evidence)
    predictions, quarantined = [], []
    for scenario_id in sorted(scenarios):
        result = run_extraction(scenarios[scenario_id], set(dataset.known_entities),
                                extraction_run_id=run_id, extracted_at=extracted_at)
        predictions.extend(result.accepted)
        quarantined.extend(result.quarantined)
    cohorts = defaultdict(list)
    for case in selected:
        cohorts[(case.sample, label_status(case))].append(case)
    source_by_signal = {p.signal_id: p.source_id for p in predictions}
    views = []
    for (sample, status), cases in sorted(cohorts.items()):
        ids = {c.evidence.source_id for c in cases}
        views.append({"sample": sample, "label_status": status, "split": split,
                      "metrics": evaluate(sorted(cases, key=lambda c: c.evidence.source_id),
                                          [p for p in predictions if p.source_id in ids],
                                          [q for q in quarantined if q.source_id in ids], config,
                                          source_by_signal_id=source_by_signal)})
    report = {
        "report_version": EVALUATOR_VERSION, "dataset_id": dataset.dataset_id,
        "dataset_sha256": dataset_sha, "code_sha256": code_sha,
        "extraction_run_id": run_id, "extracted_at": extracted_at.isoformat(),
        "clock": "simulated: latest selected source availability + 1 second",
        "extractor_version": DEFAULT_EXTRACTOR_VERSION,
        "extraction_config_version": DEFAULT_EXTRACTION_CONFIG_VERSION,
        "signal_schema_version": "0.1.0", "annotation_schema_version": dataset.schema_version,
        "metric_config": asdict(config), "python_version": platform.python_version(),
        "dependency_versions": {name: version(name) for name in ("pydantic", "jsonschema", "pandas")},
        "split": split, "n_notes": len(selected), "annotation_status": dict(statuses),
        "proposed_minimum_d2_size": 800, "below_proposed_size": len(selected) < 800,
        "provisional": bool(statuses["provisional"]), "gold_mode": require_gold,
        "natural_prevalence_available": any(c.sample == "natural_prevalence" for c in selected),
        "views": views,
        "limitations": [
            "Synthetic extraction evaluation only; no forecast lift is measured.",
            "Label provenance is declarative metadata, not independent verification of annotation work.",
            "Grounding is annotation-relative: a matching asserted value and a citation covering annotated support are both required.",
            "Error categories overlap; percentages must not be added together. Null metrics have zero eligible denominators.",
            "Duplicate counts concern multiple outputs for one source; cross-note business-event deduplication is not scored.",
        ],
        "mandatory_final_poc_caveat": POC_CAVEAT,
    }
    if statuses["provisional"]:
        report["limitations"].append("Provisional labels are drafts, not independently human-adjudicated gold.")
    if split == "dev":
        report["limitations"].append("This is a development evaluation, not a blind held-out test result.")
    if len(selected) < 800:
        report["limitations"].append("The evaluated sample is below the proposed 800-note D2 minimum; treat it as a mechanics demonstration.")
    if not report["natural_prevalence_available"]:
        report["limitations"].append("No natural-prevalence sample was provided; challenge-set scores do not estimate deployment prevalence.")
    return report, predictions, quarantined


def _value(metric: dict) -> str:
    value = metric["value"]
    return "N/A" if value is None else f"{value:.4f}"


def render_markdown(report: dict) -> str:
    lines = [f"# Extraction evaluation: {report['dataset_id']}", "",
             f"Split: **{report['split']}**. Notes: **{report['n_notes']}**. "
             f"Provisional labels present: **{report['provisional']}**.", "",
             f"Dataset SHA-256: `{report['dataset_sha256']}`.",
             f"Extractor: `{report['extractor_version']}`. Evaluator: `{report['report_version']}`.", ""]
    for view in report["views"]:
        m = view["metrics"]
        lines.extend([f"## {view['sample']} / {view['label_status']}", "",
                      "| Metric | Value | Denominator |", "|---|---:|---:|"])
        selected = {
            "Actionable event macro-F1": m["actionable_event_detection"]["macro_f1"],
            "Signal-type accuracy": m["signal_type"]["accuracy"],
            "Direction accuracy": m["direction"]["accuracy"],
            "Schema valid-record rate": m["schema_valid_record_rate"],
            "Negation subset F1 (negated=true)": m["negation_subset"]["per_class"]["True"]["f1"],
            "Conditional subset F1 (CONDITIONAL)": m["conditional_subset"]["per_class"]["CONDITIONAL"]["f1"],
            "Temporal exact match": m["temporal"]["exact_match"],
            "Temporal mean interval IoU": m["temporal"]["mean_interval_iou"],
            "Entity accuracy (resolvable)": m["entity"]["resolvable_accuracy"],
            "Unsupported-inference rate (annotation-relative)": m["grounding"]["unsupported_inference_rate"],
            "Evidence-span coverage": m["grounding"]["evidence_span_coverage"],
            "Abstention precision": m["abstention"]["precision"],
            "Abstention recall": m["abstention"]["recall"],
        }
        lines.extend(f"| {name} | {_value(metric)} | {metric['denominator']} |" for name, metric in selected.items())
        lines.extend(["", "Denominators follow each metric's definition (macro-F1: supported classes;",
                      "F1: 2TP+FP+FN; temporal: notes with annotated intervals; grounding: field assertions).", "",
                      "### Field metrics", "", "| Field | Correct / scored | Accuracy | Precision | Recall |",
                      "|---|---:|---:|---:|---:|"])
        for name, metrics in m["fields"].items():
            accuracy = metrics["accuracy"]
            lines.append(f"| {name} | {accuracy['numerator']} / {accuracy['denominator']} | {_value(accuracy)} "
                         f"| {_value(metrics['precision'])} | {_value(metrics['recall'])} |")
        lines.extend(["", "### Error taxonomy", "", "| Error | Notes |", "|---|---:|"])
        lines.extend(f"| {name} | {count} |" for name, count in m["error_taxonomy"].items())
        lines.append("")
    lines.extend(["## Interpretation limits", ""])
    lines.extend(f"- {text}" for text in report["limitations"])
    lines.extend(["", "Full denominators, per-class precision/recall/F1, per-source errors, versions, and",
                  "configuration are in `report.json`. The frozen input is `dataset_snapshot.json`.", "",
                  "## Required final POC caveat", "",
                  "This is the project's required final-report wording; this extraction-only run",
                  "does not establish its forecast-lift premise.", "", "> " + POC_CAVEAT, ""])
    return "\n".join(lines)


def write_bundle(dataset: AnnotationDataset, output_dir: Path, **kwargs) -> Path:
    report, predictions, quarantined = run_evaluation(dataset, **kwargs)
    destination = output_dir / report["extraction_run_id"]
    destination.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "report.json": json.dumps(report, indent=2, sort_keys=True) + "\n",
        "report.md": render_markdown(report),
        "dataset_snapshot.json": json.dumps(snapshot_payload(dataset), indent=2, sort_keys=True) + "\n",
        "predictions.jsonl": "".join(p.model_dump_json() + "\n" for p in predictions),
        "quarantine.jsonl": "".join(json.dumps(asdict(q), sort_keys=True) + "\n" for q in quarantined),
    }
    # Identical reruns are allowed; different content never overwrites a saved run.
    for name, content in artifacts.items():
        path = destination / name
        if path.exists() and path.read_text(encoding="utf-8") != content:
            raise FileExistsError(f"Conflicting existing evaluation artifact: {path}")
    for name, content in artifacts.items():
        (destination / name).write_text(content, encoding="utf-8", newline="\n")
    return destination
