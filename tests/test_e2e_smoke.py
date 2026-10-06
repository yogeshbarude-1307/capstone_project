"""End-to-end smoke test (docs/12 Milestone 11): the full pipeline must
complete without manual intervention on a fresh dataset and produce every
artifact listed in docs/00 Q6."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dsfs.config import REPO_ROOT, Settings
from dsfs.orchestrate import load_run_config, run_e2e


@pytest.fixture
def smoke_settings(tmp_path: Path) -> Settings:
    return Settings(
        data_raw_dir=tmp_path / "raw",
        data_interim_dir=tmp_path / "interim",
        data_processed_dir=tmp_path / "processed",
        reports_dir=tmp_path / "reports",
    )


def test_e2e_smoke_config_completes_and_produces_every_artifact(smoke_settings: Settings):
    run_config = load_run_config(REPO_ROOT / "configs" / "e2e_smoke.json")
    manifest = run_e2e(smoke_settings, run_config)

    expected_steps = {"synth", "extraction", "evaluation", "features", "forecast", "drift", "lineage"}
    assert expected_steps.issubset(manifest["steps"])

    expected_artifacts = {
        "d0_demand", "d1_notes", "d1_ground_truth", "generator_config",
        "signal_ledger", "extraction_evaluation_report", "d3_features",
        "forecast_report", "forecast_ablation_report", "drift_report",
        "lineage_sample",
    }
    assert expected_artifacts.issubset(manifest["artifacts"])

    for name, info in manifest["artifacts"].items():
        assert info["sha256"] is not None, f"artifact {name} missing or unreadable"

    assert manifest["steps"]["features"]["schema_failures"] == 0
    assert manifest["steps"]["lineage"]["n_traced"] > 0
    assert manifest["steps"]["drift"]["detected"] in (True, False)  # ran, not skipped
    assert manifest["code_sha256"]


def test_e2e_smoke_manifest_is_valid_json_on_disk(smoke_settings: Settings, tmp_path: Path):
    run_config = load_run_config(REPO_ROOT / "configs" / "e2e_smoke.json")
    manifest = run_e2e(smoke_settings, run_config)
    manifest_path = smoke_settings.reports_dir / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    reloaded = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert reloaded["steps"]["extraction"]["accepted"] > 0


def test_e2e_smoke_schema_failure_aborts_run(smoke_settings: Settings, monkeypatch):
    """The orchestrator must not silently continue past a broken D3 build."""
    import dsfs.orchestrate as orch

    def _fake_build_d3(settings, *, extraction_run_id, **kwargs):
        return smoke_settings.data_processed_dir / "d3_features.parquet", 10, 1

    monkeypatch.setattr(orch, "build_d3", _fake_build_d3)
    run_config = load_run_config(REPO_ROOT / "configs" / "e2e_smoke.json")
    with pytest.raises(RuntimeError, match="schema failures"):
        run_e2e(smoke_settings, run_config)
