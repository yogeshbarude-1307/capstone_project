"""Layered monitors (docs/10): each fires on its own scenario, silent on
unrelated ones; the PIT-violation count stays zero on a correct pipeline."""

from __future__ import annotations

import random
import sys
from pathlib import Path

import pandas as pd
import pytest

from dsfs.drift.monitors import (
    count_pit_violations,
    monitor_note_length,
    monitor_signal_type_mix,
    monitor_source_type_mix,
)
from dsfs.extraction.pipeline import run_and_persist
from dsfs.features.pipeline import build_d3
from dsfs.lineage import load_lineage_inputs
from dsfs.config import Settings
from dsfs.synth.config import GeneratorConfig
from dsfs.synth.entities import generate_entities
from dsfs.synth.generator import generate_dataset, write_dataset


def _run_pipeline(tmp_path: Path, **config_kwargs):
    settings = Settings(
        data_raw_dir=tmp_path / "raw", data_interim_dir=tmp_path / "interim",
        data_processed_dir=tmp_path / "processed", reports_dir=tmp_path / "reports",
    )
    settings.ensure_dirs()
    config = GeneratorConfig(seed=6, n_entities=10, n_weeks=40, **config_kwargs)
    dataset = generate_dataset(config)
    write_dataset(dataset, settings.data_raw_dir)
    known_entities = set(generate_entities(config))
    ledger_path = settings.data_processed_dir / "signal_ledger.jsonl"
    result = run_and_persist(dataset.d1_notes, known_entities, ledger_path)
    d3_path, _, schema_failures = build_d3(settings, extraction_run_id=result.extraction_run_id)
    assert schema_failures == 0
    return settings, dataset, result, d3_path


def _split_by_week(notes, config, inject_at_week):
    before, after = [], []
    for n in notes:
        week = (n.authored_at.date() - config.start_date).days // 7
        (before if week < inject_at_week else after).append(n)
    return before, after


def test_note_length_monitor_fires_on_note_length_shift(tmp_path):
    inject_at = 20
    settings, dataset, result, d3_path = _run_pipeline(
        tmp_path, drift_scenario="note_length_shift", drift_inject_at_week=inject_at,
    )
    before, after = _split_by_week(dataset.d1_notes, dataset.config, inject_at)
    result_monitor = monitor_note_length(before, after)
    assert result_monitor.p_value < 0.05
    assert result_monitor.effect_size != 0


def test_note_length_monitor_much_weaker_signal_without_scenario(tmp_path):
    """A single arbitrary reference/monitored split can show natural
    composition differences (e.g. more reversals appear later in the
    horizon) even with no seeded scenario — this is exactly why docs/10
    mandates calibrating on no-drift windows first (see calibration.py),
    rather than trusting a bare p<0.05 on one split. This test only checks
    the effect is much weaker than the seeded-shift case, not that it's zero.
    """
    inject_at = 20
    settings_none, dataset_none, _, _ = _run_pipeline(tmp_path / "none", drift_scenario="none")
    settings_shift, dataset_shift, _, _ = _run_pipeline(tmp_path / "shift", drift_scenario="note_length_shift", drift_inject_at_week=inject_at)

    before_none, after_none = _split_by_week(dataset_none.d1_notes, dataset_none.config, inject_at)
    before_shift, after_shift = _split_by_week(dataset_shift.d1_notes, dataset_shift.config, inject_at)

    none_result = monitor_note_length(before_none, after_none)
    shift_result = monitor_note_length(before_shift, after_shift)
    assert abs(shift_result.effect_size) > abs(none_result.effect_size)


def test_source_type_mix_monitor_fires_on_source_type_shift(tmp_path):
    inject_at = 15
    settings, dataset, result, d3_path = _run_pipeline(
        tmp_path, drift_scenario="source_type_mix_shift", drift_inject_at_week=inject_at,
    )
    before, after = _split_by_week(dataset.d1_notes, dataset.config, inject_at)
    result_monitor = monitor_source_type_mix(before, after)
    assert result_monitor.p_value < 0.05
    assert result_monitor.effect_size > 0.1


def test_pit_violation_count_is_zero_on_correct_pipeline(tmp_path):
    settings, dataset, result, d3_path = _run_pipeline(tmp_path)
    d3 = pd.read_parquet(d3_path)
    signals_by_id, sources = load_lineage_inputs(
        settings.data_processed_dir / "signal_ledger.jsonl",
        settings.data_raw_dir / "d1_notes.jsonl",
        extraction_run_id=result.extraction_run_id,
    )
    assert count_pit_violations(d3, signals_by_id, sources) == 0


def test_pit_violation_count_detects_a_real_injected_violation(tmp_path):
    """Sanity check that the checker isn't vacuously always zero: forge a
    signal whose source becomes available strictly after the row's cutoff."""
    settings, dataset, result, d3_path = _run_pipeline(tmp_path)
    d3 = pd.read_parquet(d3_path)
    signals_by_id, sources = load_lineage_inputs(
        settings.data_processed_dir / "signal_ledger.jsonl",
        settings.data_raw_dir / "d1_notes.jsonl",
        extraction_run_id=result.extraction_run_id,
    )
    rows_with_signals = d3[d3["contributing_signal_ids"].apply(lambda ids: len(ids) > 0)]
    assert not rows_with_signals.empty
    sid = rows_with_signals.iloc[0]["contributing_signal_ids"][0]
    record = signals_by_id[sid]
    future_source = sources[record.source_id].model_copy(
        update={"available_at": pd.Timestamp("2999-01-01", tz="UTC").to_pydatetime()}
    )
    sources_with_violation = dict(sources)
    sources_with_violation[record.source_id] = future_source
    assert count_pit_violations(d3, signals_by_id, sources_with_violation) > 0
