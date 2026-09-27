"""Freshness measurement: feature-layer staleness respects PIT; extraction-layer
processing latency is always non-negative."""

from __future__ import annotations

import pandas as pd

from dsfs.extraction.ledger import read_ledger
from dsfs.freshness import (
    processing_latency_days,
    summarize_feature_staleness,
    summarize_processing_latency,
)
from dsfs.lineage import load_lineage_inputs
from dsfs.models.signal_record import SignalRecord


def test_processing_latency_never_negative(real_pipeline_run):
    signals_by_id, sources = load_lineage_inputs(
        real_pipeline_run["ledger_path"], real_pipeline_run["notes_path"],
        extraction_run_id=real_pipeline_run["extraction_run_id"],
    )
    for signal in signals_by_id.values():
        latency = processing_latency_days(signal, sources[signal.source_id])
        assert latency >= 0


def test_summarize_processing_latency_produces_populated_summary(real_pipeline_run):
    signals_by_id, sources = load_lineage_inputs(
        real_pipeline_run["ledger_path"], real_pipeline_run["notes_path"],
        extraction_run_id=real_pipeline_run["extraction_run_id"],
    )
    summary = summarize_processing_latency(list(signals_by_id.values()), sources)
    assert summary.n == len(signals_by_id)
    assert summary.mean_days is not None
    assert summary.mean_days >= 0
    assert summary.max_days >= summary.median_days >= 0


def test_summarize_processing_latency_empty_input():
    summary = summarize_processing_latency([], {})
    assert summary.n == 0
    assert summary.mean_days is None


def test_summarize_feature_staleness_reuses_existing_d3_columns(real_pipeline_run):
    d3 = pd.read_parquet(real_pipeline_run["d3_path"])
    summary = summarize_feature_staleness(d3)
    assert "days_since_latest_signal" in summary
    assert "staleness_status_counts" in summary
    total_counted = sum(summary["staleness_status_counts"].values())
    assert total_counted == len(d3)


def test_summarize_feature_staleness_handles_missing_columns():
    empty = pd.DataFrame({"entity_key": ["CUST-0001"]})
    summary = summarize_feature_staleness(empty)
    assert summary["days_since_latest_signal"]["n"] == 0
    assert summary["staleness_status_counts"] == {}
