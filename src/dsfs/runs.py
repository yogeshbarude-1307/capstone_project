"""Isolated local snapshots and atomic completed-run discovery."""
from __future__ import annotations
from contextlib import contextmanager
from dataclasses import asdict
import json
import os
from pathlib import Path
import re
from dsfs.config import Settings

def atomic_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, default=str, allow_nan=False), encoding="utf-8")
    os.replace(temporary, path)

def run_settings(settings: Settings, run_id: str):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", run_id):
        raise ValueError("Invalid run identifier")
    root = settings.reports_dir / "runs" / run_id
    return settings.model_copy(update={"data_raw_dir": root/"raw", "data_interim_dir":root/"interim",
                                      "data_processed_dir":root/"processed", "reports_dir":root/"reports"})

@contextmanager
def pipeline_lock(settings: Settings):
    settings.reports_dir.mkdir(parents=True, exist_ok=True)
    path = settings.reports_dir / ".pipeline.lock"
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise RuntimeError("Another pipeline run is active; concurrent runs are rejected") from exc
    try:
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        yield
    finally:
        path.unlink(missing_ok=True)

def completed_runs(settings):
    root = settings.reports_dir / "runs"
    results = []
    for manifest in root.glob("*/reports/manifest.json"):
        data = json.loads(manifest.read_text(encoding="utf-8"))
        if data.get("status") == "complete":
            results.append(data)
    return sorted(results, key=lambda m:m["finished_at"], reverse=True)

def load_run_service(settings, run_id):
    import pandas as pd
    from dsfs.extraction.ledger import read_ledger
    from dsfs.models.signal_record import SignalRecord
    from dsfs.models.source_evidence import SourceEvidence
    from dsfs.features.service import DemandFeatureService
    from dsfs.forecast.harness import ForecastConfig
    s = run_settings(settings, run_id)
    path = s.reports_dir/"manifest.json"
    if not path.is_file():
        raise KeyError("Unknown completed run")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("status") != "complete":
        raise KeyError("Run is not complete")
    sources = {v.source_id:v for v in [SourceEvidence.model_validate_json(line) for line in
               (s.data_raw_dir/"d1_notes.jsonl").read_text(encoding="utf-8").splitlines() if line]}
    signals = [SignalRecord.model_validate(r) for r in read_ledger(s.data_processed_dir/"signal_ledger.jsonl")]
    cfg = manifest.get("forecast_config", {})
    return DemandFeatureService(pd.read_parquet(s.data_raw_dir/"d0_tabular_demand.parquet"),
        signals, sources, run_id, delays=manifest.get("publication_delays", {}), forecast_config=ForecastConfig(**cfg))
