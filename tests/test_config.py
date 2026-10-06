from dsfs.config import REPO_ROOT, get_settings


def test_settings_default_paths_are_local_and_under_repo_root():
    s = get_settings()
    for d in (s.data_raw_dir, s.data_interim_dir, s.data_processed_dir, s.reports_dir, s.schema_dir):
        assert REPO_ROOT in d.parents or d == REPO_ROOT

    # No network-facing defaults anywhere in config (offline/local-only
    # constraint — docs/05-technology-decision-matrix.md).
    assert s.llm_extraction_enabled is False
    assert s.local_llm_model_path is None


def test_schema_dir_contains_the_three_canonical_contracts():
    s = get_settings()
    names = {p.name for p in s.schema_dir.glob("*.schema.json")}
    assert names == {
        "source_evidence.schema.json",
        "signal_record.schema.json",
        "forecast_feature.schema.json",
        "demand_feature.schema.json",
    }


def test_ensure_dirs_creates_missing_directories(tmp_path, monkeypatch):
    from dsfs.config import Settings

    s = Settings(
        data_raw_dir=tmp_path / "raw",
        data_interim_dir=tmp_path / "interim",
        data_processed_dir=tmp_path / "processed",
        reports_dir=tmp_path / "reports",
    )
    s.ensure_dirs()
    assert s.data_raw_dir.is_dir()
    assert s.data_interim_dir.is_dir()
    assert s.data_processed_dir.is_dir()
    assert s.reports_dir.is_dir()
