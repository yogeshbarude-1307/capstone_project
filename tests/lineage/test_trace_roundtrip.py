"""Lineage-trace correctness: a feature row must resolve back to its exact
source note text (docs/10 Milestone 10 acceptance criterion)."""

from __future__ import annotations

from dsfs.lineage import load_lineage_inputs, trace_feature_row, trace_sample


def test_traced_signal_evidence_span_is_substring_of_real_raw_text(real_pipeline_run):
    traces = trace_sample(
        real_pipeline_run["d3_path"],
        real_pipeline_run["ledger_path"],
        real_pipeline_run["notes_path"],
        extraction_run_id=real_pipeline_run["extraction_run_id"],
        n=20,
    )
    assert traces, "expected at least one feature row with contributing signals"
    resolved_any = False
    for trace in traces:
        assert trace.is_complete
        for signal in trace.signals:
            assert signal.evidence_span in signal.raw_text
            resolved_any = True
    assert resolved_any


def test_trace_sample_is_deterministic_given_seed(real_pipeline_run):
    a = trace_sample(
        real_pipeline_run["d3_path"], real_pipeline_run["ledger_path"], real_pipeline_run["notes_path"],
        extraction_run_id=real_pipeline_run["extraction_run_id"], n=5, seed=1,
    )
    b = trace_sample(
        real_pipeline_run["d3_path"], real_pipeline_run["ledger_path"], real_pipeline_run["notes_path"],
        extraction_run_id=real_pipeline_run["extraction_run_id"], n=5, seed=1,
    )
    assert [t.entity_key for t in a] == [t.entity_key for t in b]
    assert [t.forecast_cutoff for t in a] == [t.forecast_cutoff for t in b]


def test_trace_feature_row_drops_unresolvable_signal_ids_without_raising():
    signals_by_id, sources = {}, {}
    row = {"entity_key": "CUST-0001", "forecast_cutoff": "2023-01-02", "contributing_signal_ids": ["missing-sig"]}
    trace = trace_feature_row(row, signals_by_id, sources)
    assert trace.signals == []
    assert trace.is_complete is False


def test_load_lineage_inputs_filters_to_the_requested_run(real_pipeline_run):
    signals_by_id, sources = load_lineage_inputs(
        real_pipeline_run["ledger_path"], real_pipeline_run["notes_path"],
        extraction_run_id=real_pipeline_run["extraction_run_id"],
    )
    assert all(s.extraction_run_id == real_pipeline_run["extraction_run_id"] for s in signals_by_id.values())
    assert len(sources) > 0
