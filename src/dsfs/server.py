"""FastAPI dashboard backend for the DSFS POC.

Serves the single-page dashboard at GET / and provides REST endpoints
that read from local pipeline-output files. All offline/localhost only.

    dsfs-server          # http://127.0.0.1:8000
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from dsfs.config import REPO_ROOT, Settings, get_settings

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="DSFS Dashboard", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# ---------------------------------------------------------------------------
# JSON serialiser — handles NaN / Infinity that appear in drift reports
# ---------------------------------------------------------------------------

def _safe(obj: Any) -> Any:
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    return obj


def _clean(data: Any) -> Any:
    if isinstance(data, dict):
        return {k: _clean(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_clean(v) for v in data]
    if isinstance(data, float):
        return _safe(data)
    return data


def _json(data: Any) -> JSONResponse:
    return JSONResponse(content=_clean(data))


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------

def _settings() -> Settings:
    return get_settings()


def _manifest(run_id: str | None = None) -> dict:
    from dsfs.runs import run_settings
    path = (run_settings(_settings(), run_id).reports_dir if run_id else _settings().reports_dir) / "manifest.json"
    if not path.exists():
        if run_id: raise HTTPException(404,"Unknown completed run")
        return {}
    raw = path.read_text(encoding="utf-8")
    # json.loads rejects NaN — replace bare NaN with null first
    raw = re.sub(r"\bNaN\b", "null", raw)
    data = json.loads(raw)
    if data.get("status") != "complete":
        if run_id: raise HTTPException(404,"Run is not complete")
        return {}
    return data

def _snapshot(run_id=None):
    from dsfs.runs import run_settings
    manifest = _manifest(run_id)
    return run_settings(_settings(), manifest["run_id"]) if manifest.get("run_id") else _settings()


def _load_signals(run_id=None) -> list[dict]:
    if not _manifest(run_id): return []
    s = _snapshot(run_id)
    ledger = s.data_processed_dir / "signal_ledger.jsonl"
    notes_path = s.data_raw_dir / "d1_notes.jsonl"
    if not ledger.exists():
        return []

    # Load notes indexed by source_id
    notes: dict[str, dict] = {}
    if notes_path.exists():
        with notes_path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    obj = json.loads(line)
                    notes[obj["source_id"]] = obj

    # Merge signals with notes
    rows = []
    selected = _manifest(run_id).get("run_id")
    with ledger.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            sig = json.loads(line)
            if selected and sig.get("extraction_run_id") != selected:
                continue
            note = notes.get(sig.get("source_id"), {})
            rows.append({**sig,
                         "raw_text": note.get("raw_text", ""),
                         "source_type": note.get("source_type", ""),
                         "authored_at": note.get("authored_at", ""),
                         "available_at": note.get("available_at", "")})
    return rows


def _load_extraction_report(run_id=None) -> dict:
    """Load the most recent extraction eval report.json."""
    if not _manifest(run_id): return {}
    eval_dir = _snapshot(run_id).reports_dir / "extraction"
    if not eval_dir.exists():
        return {}
    candidates = sorted(eval_dir.glob("*/report.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        return {}
    return json.loads(candidates[0].read_text(encoding="utf-8"))


def _independent_review(manifest):
    """Separate reviewer evidence from the immutable synthetic run bundle."""
    metadata = manifest.get("steps", {}).get("independent_review", {})
    if not metadata: return {"status": "not_prepared"}
    root = _settings().reports_dir / "independent-reviews" / manifest["run_id"]
    ai_draft = None
    human_review = None
    for path in sorted(root.glob("*/report.json"), reverse=True):
        report = json.loads(path.read_text(encoding="utf-8"))
        snapshot = json.loads(path.with_name("dataset_snapshot.json").read_text(encoding="utf-8"))
        original = json.loads(Path(metadata["path"]).read_text(encoding="utf-8"))
        ids = lambda d: {c["evidence"]["source_id"]: c["evidence"] for c in d["cases"]}
        if ids(snapshot) != ids(original): continue
        if report.get("extractor_version") != metadata["extractor_version"]: continue
        if report.get("code_sha256") != metadata.get("code_sha256"): continue
        if report.get("provisional") and report.get("annotation_status") == {"provisional": 50}:
            annotators = sorted({annotator for case in snapshot.get("cases", [])
                                 if case.get("label_origin") == "assistant_draft"
                                 for annotator in case.get("annotator_ids", [])})
            if len(annotators) == 1:
                ai_draft = {"status": "evaluated", "provenance": "cross-model AI draft",
                            "annotator_ids": annotators, "views": report["views"],
                            "report_path": str(path), "provisional": True}
            continue
        if report.get("annotation_status") != {"human_single": 50}: continue
        if len(report.get("reviewer_ids",[])) != 1: continue
        human_review = {"status": "reviewed", "provenance": "independent single-person review (declared)",
                        "views": report["views"], "report_path": str(path)}
    if human_review:
        if ai_draft: human_review["ai_draft"] = ai_draft
        return human_review
    result = dict(metadata)
    if ai_draft: result["ai_draft"] = ai_draft
    return result


def _load_lineage(entity_key: str, cutoff_str: str, run_id=None) -> dict:
    s = _snapshot(run_id)
    ledger = s.data_processed_dir / "signal_ledger.jsonl"
    notes_path = s.data_raw_dir / "d1_notes.jsonl"
    d3_path = s.data_processed_dir / "d3_features.parquet"

    if not ledger.exists() or not d3_path.exists():
        return {"error": "Run the pipeline first to generate data."}

    # Get latest run_id
    run_id = None
    with ledger.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                run_id = json.loads(line).get("extraction_run_id")
    if not run_id:
        return {"error": "No extraction runs found."}

    try:
        from datetime import datetime, timezone
        from dsfs.lineage import load_lineage_inputs
        from dsfs.features.access import load_feature_store

        cutoff = datetime.fromisoformat(cutoff_str)
        if cutoff.tzinfo is None: cutoff = cutoff.replace(tzinfo=timezone.utc)
        from dsfs.runs import load_run_service
        service = load_run_service(_settings(), run_id)
        feat = service.row(entity_key, cutoff)
        signal_ids = feat.contributing_signal_ids or []
        if not signal_ids:
            return {"entity_key": entity_key, "forecast_cutoff": cutoff_str,
                    "message": "No contributing signals at this cutoff."}

        signals_by_id, sources = load_lineage_inputs(ledger, notes_path, extraction_run_id=run_id)

        result_signals = []
        for sid in signal_ids:
            rec = signals_by_id.get(sid)
            if not rec:
                continue
            src = sources.get(rec.source_id)
            span = ""
            if src:
                span = src.raw_text[rec.evidence_ref.char_start:rec.evidence_ref.char_end]
            result_signals.append({
                "signal_id": rec.signal_id,
                "signal_type": str(rec.signal_type),
                "direction": str(rec.direction),
                "business_certainty": str(rec.business_certainty),
                "source_id": rec.source_id,
                "raw_text": src.raw_text if src else "",
                "evidence_span": span,
                "char_start": rec.evidence_ref.char_start,
                "char_end": rec.evidence_ref.char_end,
                "authored_at": src.authored_at.isoformat() if src else "",
            })

        return {
            "entity_key": entity_key,
            "forecast_cutoff": cutoff_str,
            "extraction_run_id": run_id,
            "contributing_signal_ids": signal_ids,
            "signals": result_signals,
        }
    except Exception as exc:
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/status")
def api_status(run_id: str | None = None):
    manifest = _manifest(run_id)
    if not manifest:
        return _json({"ready": False, "message": "No pipeline run found. Click 'Run Pipeline'."})
    steps = manifest.get("steps", {})
    synth = steps.get("synth", {})
    ext = steps.get("extraction", {})
    return _json({
        "ready": True,
        "run_id": ext.get("extraction_run_id", ""),
        "started_at": manifest.get("started_at", ""),
        "finished_at": manifest.get("finished_at", ""),
        "n_entities": synth.get("n_entities", 0),
        "n_notes": synth.get("n_notes", 0),
        "n_weeks": synth.get("n_weeks", 0),
        "accepted": ext.get("accepted", 0),
        "quarantined": ext.get("quarantined", 0),
        "freshness": steps.get("freshness", {}),
    })


@app.get("/api/signals")
def api_signals(run_id: str | None = None):
    return _json(_load_signals(run_id))


@app.get("/api/signals/{signal_id}")
def api_signal_detail(signal_id: str, run_id: str | None = None):
    rows = _load_signals(run_id)
    for row in rows:
        if row.get("signal_id") == signal_id:
            return _json(row)
    raise HTTPException(status_code=404, detail="Signal not found")


@app.get("/api/forecast")
def api_forecast(run_id: str | None = None):
    manifest = _manifest(run_id)
    if not manifest:
        return _json({"error": "No pipeline run found."})
    steps = manifest.get("steps", {})
    return _json({**steps.get("forecast", {}), "uncertainty": steps.get("forecast_uncertainty", {}),
                  "segments": steps.get("forecast_segments", {})})


@app.get("/api/extraction")
def api_extraction(run_id: str | None = None):
    report = _load_extraction_report(run_id)
    if not report:
        return _json({"error": "No extraction evaluation report found."})
    manifest = _manifest(run_id)
    ext = manifest.get("steps", {}).get("extraction", {}) if manifest else {}

    # Flatten views[0].metrics for easy consumption
    metrics = {}
    views = report.get("views", [])
    if views:
        metrics = views[0].get("metrics", {})

    return _json({
        "accepted": ext.get("accepted", report.get("n_notes", 0)),
        "quarantined": ext.get("quarantined", 0),
        "n_notes": report.get("n_notes", 0),
        "dataset_id": report.get("dataset_id", ""),
        "provisional": report.get("provisional", True),
        "metrics": metrics,
        "limitations": report.get("limitations", []),
        "mandatory_caveat": report.get("mandatory_final_poc_caveat", ""),
        "independent_review": _independent_review(manifest),
    })


@app.get("/api/drift")
def api_drift(run_id: str | None = None):
    manifest = _manifest(run_id)
    if not manifest:
        return _json({"error": "No pipeline run found."})
    return _json(manifest.get("steps", {}).get("drift", {}))


@app.get("/api/lineage")
def api_lineage(entity: str = "", cutoff: str = "2024-06-03T00:00:00Z", run_id: str | None = None):
    if not entity:
        s = _snapshot(run_id)
        path = s.data_raw_dir / "d0_tabular_demand.parquet"
        if not path.exists(): return _json({"entities": [], "cutoffs": []})
        import pandas as pd
        d0 = pd.read_parquet(path)
        return _json({"entities": sorted(d0.entity_key.unique()), "cutoffs": [
            pd.Timestamp(d).tz_localize("UTC").isoformat() for d in sorted(d0.period_start.unique())]})
    return _json(_load_lineage(entity, cutoff, run_id))

@app.get("/api/runs")
def api_runs():
    from dsfs.runs import completed_runs
    return _json([{"run_id":m["run_id"],"finished_at":m["finished_at"]} for m in completed_runs(_settings())])

def _resolve_feature_service(run_id):
    from dsfs.runs import load_run_service
    return load_run_service(_settings(), run_id)

from dsfs.features.http import feature_router
app.include_router(feature_router(_resolve_feature_service))


@app.post("/api/pipeline/run")
def api_run_pipeline():
    from dsfs.orchestrate import load_run_config, run_e2e
    settings = _settings()
    config_path = REPO_ROOT / "configs" / "e2e_smoke.json"
    run_config = load_run_config(config_path if config_path.exists() else None)
    try:
        manifest = run_e2e(settings, run_config)
        return _json({"ok": True, "run_id":manifest["run_id"], "steps": list(manifest.get("steps", {}).keys())})
    except Exception as exc:
        if "concurrent runs" in str(exc):
            raise HTTPException(409, str(exc)) from exc
        return _json({"ok": False, "error": str(exc)})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:  # pragma: no cover
    import uvicorn
    uvicorn.run("dsfs.server:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
