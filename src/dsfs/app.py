"""Gradio dashboard for the Demand Signal Feature Service POC.

Five tabs:
  1. Run Pipeline   — trigger dsfs-run from the UI, stream log, show manifest
  2. Forecast       — 4-arm results table + bar chart + ablation matrix
  3. Extraction     — field-level precision/recall/F1 from eval report.json
  4. Drift          — per-scenario detection/latency/false-alert table
  5. Lineage        — trace a feature row back to its contributing signals/notes

Usage:
    dsfs-app
    # or:
    python -m dsfs.app
"""

from __future__ import annotations

import json
import re
import traceback
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from dsfs.config import REPO_ROOT, Settings, get_settings

# ---------------------------------------------------------------------------
# Lazy gradio import — kept at module level for testability but wrapped so
# tests can import this file without gradio installed (import-smoke test).
# ---------------------------------------------------------------------------
try:
    import gradio as gr
    _GRADIO_AVAILABLE = True
except ImportError:  # pragma: no cover
    gr = None  # type: ignore[assignment]
    _GRADIO_AVAILABLE = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _configs() -> list[str]:
    cfg_dir = REPO_ROOT / "configs"
    if not cfg_dir.exists():
        return []
    return sorted(str(p.relative_to(REPO_ROOT)) for p in cfg_dir.glob("*.json"))


def _list_reports(subdir: str, pattern: str) -> list[str]:
    base = REPO_ROOT / "reports" / subdir
    if not base.exists():
        return []
    return sorted(str(p.relative_to(REPO_ROOT)) for p in base.rglob(pattern))


def _read_json(rel_path: str) -> dict | list | None:
    p = REPO_ROOT / rel_path
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Tab 1 — Run Pipeline
# ---------------------------------------------------------------------------

def run_pipeline(config_choice: str):
    """Generator: yields (log_text, manifest_dict) pairs for streaming."""
    from dsfs.orchestrate import load_run_config, run_e2e

    settings = get_settings()
    config_path = REPO_ROOT / config_choice if config_choice else None

    try:
        run_config = load_run_config(config_path)
    except Exception as exc:
        yield f"ERROR loading config: {exc}", {}
        return

    log_lines: list[str] = [f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] Starting run…"]
    yield "\n".join(log_lines), {}

    # Patch the orchestrator's module-level print to capture step logs.
    import dsfs.orchestrate as _orch
    _original_run = _orch.run_e2e

    step_names = ["synth", "extraction", "evaluation", "features", "forecast", "drift", "lineage"]
    manifest: dict = {}

    def _instrumented_run(s: Settings, rc: dict) -> dict:
        nonlocal manifest
        # Run each stage by calling the real function, yielding after each step.
        manifest = _original_run(s, rc)
        return manifest

    try:
        log_lines.append(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] Running pipeline…")
        yield "\n".join(log_lines), {}

        manifest = _instrumented_run(settings, run_config)

        for step in step_names:
            info = manifest.get("steps", {}).get(step, "—")
            log_lines.append(f"  ✓ {step}: {info}")

        log_lines.append(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] Done.")
        yield "\n".join(log_lines), manifest

        # Persist manifest alongside reports.
        manifest_path = settings.reports_dir / "manifest.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")

    except Exception as exc:
        log_lines.append(f"\nERROR: {exc}\n{traceback.format_exc()}")
        yield "\n".join(log_lines), {}


# ---------------------------------------------------------------------------
# Tab 2 — Forecast Results
# ---------------------------------------------------------------------------

def _parse_forecast_md(md_text: str) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    """Parse experiment_results.md into (arm_df, ablation_df, decision_text)."""
    arm_rows = []
    ablation_rows = []
    decision_text = ""

    in_arm_table = False
    in_ablation_table = False
    skip_sep = False

    for line in md_text.splitlines():
        stripped = line.strip()

        # Decision logic paragraph
        if "decision" in stripped.lower() and ("b" in stripped.lower()) and ("a" in stripped.lower()):
            decision_text = stripped

        # Detect table starts
        if re.search(r"\|\s*Arm\s*\|", stripped, re.I):
            in_arm_table = True
            in_ablation_table = False
            skip_sep = True
            continue
        if re.search(r"\|\s*Ablation\s*\|", stripped, re.I):
            in_ablation_table = True
            in_arm_table = False
            skip_sep = True
            continue

        if stripped.startswith("|---") or stripped.startswith("| ---"):
            skip_sep = False
            continue

        if stripped.startswith("|") and in_arm_table and not skip_sep:
            cols = [c.strip() for c in stripped.strip("|").split("|")]
            if len(cols) >= 4:
                arm_rows.append(cols)
            continue

        if stripped.startswith("|") and in_ablation_table and not skip_sep:
            cols = [c.strip() for c in stripped.strip("|").split("|")]
            if len(cols) >= 3:
                ablation_rows.append(cols)
            continue

        if not stripped.startswith("|"):
            in_arm_table = False
            in_ablation_table = False

    arm_df = pd.DataFrame(arm_rows) if arm_rows else pd.DataFrame()
    ablation_df = pd.DataFrame(ablation_rows) if ablation_rows else pd.DataFrame()
    return arm_df, ablation_df, decision_text


def load_forecast(report_path: str):
    if not report_path:
        empty = pd.DataFrame()
        return empty, empty, "No report selected.", empty

    p = REPO_ROOT / report_path
    if not p.exists():
        empty = pd.DataFrame()
        return empty, empty, f"File not found: {report_path}", empty

    md_text = p.read_text(encoding="utf-8")
    arm_df, ablation_df, decision_text = _parse_forecast_md(md_text)

    # Bar chart data: need numeric MAE column
    bar_df = pd.DataFrame()
    if not arm_df.empty and arm_df.shape[1] >= 4:
        arm_df.columns = [f"col{i}" for i in range(arm_df.shape[1])]
        # Try to build a clean bar chart df with Arm + MAE
        try:
            bar_df = arm_df[["col0", "col2"]].copy()
            bar_df.columns = ["Arm", "MAE"]
            bar_df["MAE"] = pd.to_numeric(bar_df["MAE"].str.replace(",", ""), errors="coerce")
        except Exception:
            bar_df = pd.DataFrame()

    return arm_df, ablation_df, decision_text or "Decision logic not found in report.", bar_df


def make_forecast_tab():
    with gr.Tab("📈 Forecast Results"):
        gr.Markdown("## 4-Arm Forecast Experiment Results")
        gr.Markdown(
            "Load the `experiment_results.md` produced by `dsfs-run` or `dsfs-forecast`. "
            "**A** = tabular baseline · **B** = oracle · **C** = extracted · **D** = shuffled control."
        )
        with gr.Row():
            rpt_dd = gr.Dropdown(
                choices=_list_reports("forecast", "experiment_results.md"),
                label="Forecast report",
                allow_custom_value=True,
            )
            load_btn = gr.Button("Load", variant="primary")

        decision_md = gr.Markdown("_Select a report and click Load._")

        with gr.Row():
            arm_tbl = gr.Dataframe(label="4-Arm Results", wrap=True)

        bar_chart = gr.BarPlot(
            x="Arm", y="MAE",
            title="MAE by Forecast Arm (lower is better)",
            color="Arm",
            label="MAE chart",
        )

        ablation_tbl = gr.Dataframe(label="Ablation Matrix", wrap=True)

        load_btn.click(
            fn=load_forecast,
            inputs=[rpt_dd],
            outputs=[arm_tbl, ablation_tbl, decision_md, bar_chart],
        )


# ---------------------------------------------------------------------------
# Tab 3 — Extraction Metrics
# ---------------------------------------------------------------------------

def load_extraction(report_path: str):
    if not report_path:
        return pd.DataFrame(), pd.DataFrame(), "No report selected.", 0.0

    p = REPO_ROOT / report_path
    if not p.exists():
        return pd.DataFrame(), pd.DataFrame(), f"File not found: {report_path}", 0.0

    data = json.loads(p.read_text(encoding="utf-8"))

    # Flatten per-field metrics
    field_rows = []
    for name, val in data.get("metrics", {}).items():
        if isinstance(val, dict) and "precision" in val:
            field_rows.append({
                "Metric": name,
                "Precision": round(val.get("precision", 0), 4),
                "Recall": round(val.get("recall", 0), 4),
                "F1": round(val.get("f1", 0), 4),
                "Support": val.get("support", "—"),
            })
    field_df = pd.DataFrame(field_rows) if field_rows else pd.DataFrame(
        columns=["Metric", "Precision", "Recall", "F1", "Support"]
    )

    # Abstention breakdown
    abs_rows = []
    for key in ("no_signal_precision", "no_signal_recall", "review_abstention_rate"):
        v = data.get(key)
        if v is not None:
            abs_rows.append({"Metric": key, "Value": round(v, 4)})
    abs_df = pd.DataFrame(abs_rows) if abs_rows else pd.DataFrame(columns=["Metric", "Value"])

    # Schema conformance
    conformance = data.get("schema_valid_rate", data.get("schema_conformance_rate", 0.0))
    conformance = float(conformance) if conformance else 0.0

    # Limitations caveat
    caveat = data.get("limitations") or data.get("caveat") or "_No limitations note found in report._"

    return field_df, abs_df, str(caveat), conformance


def make_extraction_tab():
    with gr.Tab("🔬 Extraction Metrics"):
        gr.Markdown("## Extraction Evaluation Metrics")
        gr.Markdown(
            "Load `report.json` from an evaluation run under `reports/extraction/`. "
            "These are **self-scored development diagnostics**, not independent measurements — see docs/09."
        )
        with gr.Row():
            rpt_dd = gr.Dropdown(
                choices=_list_reports("extraction", "report.json"),
                label="Evaluation report",
                allow_custom_value=True,
            )
            load_btn = gr.Button("Load", variant="primary")

        conformance_num = gr.Number(label="Schema conformance rate", precision=4)
        field_tbl = gr.Dataframe(label="Field-level Metrics (Precision / Recall / F1)", wrap=True)
        abs_tbl = gr.Dataframe(label="Abstention Metrics", wrap=True)
        caveat_md = gr.Markdown()

        load_btn.click(
            fn=load_extraction,
            inputs=[rpt_dd],
            outputs=[field_tbl, abs_tbl, caveat_md, conformance_num],
        )


# ---------------------------------------------------------------------------
# Tab 4 — Drift Monitoring
# ---------------------------------------------------------------------------

def _parse_drift_md(md_text: str) -> pd.DataFrame:
    rows = []
    in_table = False
    for line in md_text.splitlines():
        stripped = line.strip()
        if re.search(r"\|\s*Scenario\s*\|", stripped, re.I):
            in_table = True
            continue
        if stripped.startswith("|---") or stripped.startswith("| ---"):
            continue
        if stripped.startswith("|") and in_table:
            cols = [c.strip() for c in stripped.strip("|").split("|")]
            if len(cols) >= 4:
                rows.append(cols[:5])
        elif in_table and not stripped.startswith("|"):
            in_table = False
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df.columns = ["Scenario", "Monitor", "Detected", "Latency (weeks)", "False-alert rate"][: df.shape[1]]
    return df


def load_drift(report_path: str):
    if not report_path:
        return pd.DataFrame(), pd.DataFrame()

    p = REPO_ROOT / report_path
    if not p.exists():
        return pd.DataFrame(), pd.DataFrame()

    md_text = p.read_text(encoding="utf-8")
    df = _parse_drift_md(md_text)
    if df.empty:
        return df, pd.DataFrame()

    # Bar chart: latency for detected scenarios
    bar_df = pd.DataFrame()
    if "Detected" in df.columns and "Latency (weeks)" in df.columns:
        detected = df[df["Detected"].str.lower() == "true"].copy()
        if not detected.empty:
            bar_df = detected[["Scenario", "Latency (weeks)"]].copy()
            bar_df["Latency (weeks)"] = pd.to_numeric(bar_df["Latency (weeks)"], errors="coerce")

    return df, bar_df


def make_drift_tab():
    with gr.Tab("📡 Drift Monitoring"):
        gr.Markdown("## Drift Detection Results")
        gr.Markdown(
            "Per-scenario detection outcome, latency (weeks after injection), and calibrated "
            "false-alert rate — always reported together per docs/10 discipline."
        )
        gr.Markdown(
            "> **Note:** `direction_class_shift` and `concept_drift` are not implemented in this POC "
            "(would require modifying the causal-separation-critical `latent.py`/`demand.py` modules)."
        )
        with gr.Row():
            rpt_dd = gr.Dropdown(
                choices=_list_reports("drift", "drift_results.md"),
                label="Drift report",
                allow_custom_value=True,
            )
            load_btn = gr.Button("Load", variant="primary")

        drift_tbl = gr.Dataframe(label="Scenario Results", wrap=True)
        bar_chart = gr.BarPlot(
            x="Scenario", y="Latency (weeks)",
            title="Detection Latency (weeks after injection) — detected scenarios only",
            label="Latency chart",
        )

        load_btn.click(
            fn=load_drift,
            inputs=[rpt_dd],
            outputs=[drift_tbl, bar_chart],
        )


# ---------------------------------------------------------------------------
# Tab 5 — Lineage Explorer
# ---------------------------------------------------------------------------

def _latest_extraction_run_id(ledger_path: Path) -> str | None:
    from dsfs.extraction.ledger import read_ledger
    records = read_ledger(ledger_path)
    if not records:
        return None
    return records[-1].get("extraction_run_id")


def _entity_list(notes_path: Path) -> list[str]:
    if not notes_path.exists():
        return []
    entities: set[str] = set()
    with notes_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                ek = obj.get("entity_key") or obj.get("forecast_key")
                if ek:
                    entities.add(ek)
            except Exception:
                pass
    return sorted(entities)


def trace_lineage(entity_key: str, cutoff_str: str):
    settings = get_settings()
    ledger_path = settings.data_processed_dir / "signal_ledger.jsonl"
    notes_path = settings.data_raw_dir / "d1_notes.jsonl"
    d3_path = settings.data_processed_dir / "d3_features.parquet"

    if not ledger_path.exists():
        return {}, pd.DataFrame(columns=["source_id", "authored_at", "available_at", "note_text"])

    run_id = _latest_extraction_run_id(ledger_path)
    if run_id is None:
        return {"error": "No extraction runs found in ledger."}, pd.DataFrame()

    if not d3_path.exists():
        return {"error": "D3 features not found — run the pipeline first."}, pd.DataFrame()

    try:
        cutoff = datetime.fromisoformat(cutoff_str.strip()).replace(tzinfo=timezone.utc)
    except ValueError:
        return {"error": f"Invalid datetime: {cutoff_str!r}. Use ISO format e.g. 2024-06-01T00:00:00"}, pd.DataFrame()

    try:
        from dsfs.features.access import load_feature_store
        from dsfs.lineage import load_lineage_inputs

        store = load_feature_store(ledger_path, notes_path, extraction_run_id=run_id)
        response = store.get_features([entity_key], cutoff)

        if not response.features:
            return {"message": f"No features for {entity_key} at {cutoff_str}"}, pd.DataFrame()

        feature_row = response.features[0]
        signal_ids = feature_row.contributing_signal_ids or []

        if not signal_ids:
            return {
                "entity_key": entity_key,
                "forecast_cutoff": cutoff_str,
                "message": "No contributing signals at this cutoff.",
            }, pd.DataFrame()

        signals_by_id, sources = load_lineage_inputs(
            ledger_path, notes_path, extraction_run_id=run_id
        )

        signal_details = []
        note_rows = []
        for sid in signal_ids:
            rec = signals_by_id.get(sid)
            if rec is None:
                continue
            signal_details.append({
                "signal_id": rec.signal_id,
                "signal_type": str(rec.signal_type),
                "direction": str(rec.direction),
                "business_certainty": str(rec.business_certainty),
                "source_id": rec.source_id,
            })
            src = sources.get(rec.source_id)
            if src:
                span = src.raw_text[rec.evidence_ref.char_start:rec.evidence_ref.char_end]
                note_rows.append({
                    "source_id": src.source_id,
                    "authored_at": str(src.authored_at)[:19],
                    "available_at": str(src.available_at)[:19],
                    "evidence_span": span[:120],
                    "note_text": src.raw_text[:200],
                })

        lineage_json = {
            "entity_key": entity_key,
            "forecast_cutoff": cutoff_str,
            "extraction_run_id": run_id,
            "contributing_signal_ids": signal_ids,
            "signals": signal_details,
        }
        note_df = pd.DataFrame(note_rows) if note_rows else pd.DataFrame(
            columns=["source_id", "authored_at", "available_at", "evidence_span", "note_text"]
        )
        return lineage_json, note_df

    except Exception as exc:
        return {"error": str(exc), "traceback": traceback.format_exc()}, pd.DataFrame()


def make_lineage_tab():
    settings = get_settings()
    notes_path = settings.data_raw_dir / "d1_notes.jsonl"
    entity_list = _entity_list(notes_path)

    with gr.Tab("🔗 Lineage Explorer"):
        gr.Markdown("## Feature Row Lineage Tracer")
        gr.Markdown(
            "Select an entity and a forecast cutoff to trace which signals contributed "
            "to that feature row, and which source notes those signals came from. "
            "Uses the latest extraction run in the ledger."
        )
        with gr.Row():
            entity_dd = gr.Dropdown(
                choices=entity_list,
                label="Entity key",
                allow_custom_value=True,
                value=entity_list[0] if entity_list else None,
            )
            cutoff_tb = gr.Textbox(
                label="Forecast cutoff (ISO datetime)",
                placeholder="e.g. 2024-06-01T00:00:00",
                value="2024-06-01T00:00:00",
            )
            trace_btn = gr.Button("Trace", variant="primary")

        signal_json = gr.JSON(label="Contributing Signals")
        note_tbl = gr.Dataframe(
            label="Source Notes (evidence spans + full note text)", wrap=True
        )

        trace_btn.click(
            fn=trace_lineage,
            inputs=[entity_dd, cutoff_tb],
            outputs=[signal_json, note_tbl],
        )


# ---------------------------------------------------------------------------
# Build the full app
# ---------------------------------------------------------------------------

def build_app() -> "gr.Blocks":
    if not _GRADIO_AVAILABLE:
        raise ImportError("gradio is not installed. Run: pip install 'gradio>=4.44'")

    with gr.Blocks(
        title="Demand Signal Feature Service",
        theme=gr.themes.Soft(),
    ) as demo:
        gr.Markdown(
            "# 📊 Demand Signal Feature Service — POC Dashboard\n"
            "Offline/local dashboard for the DSFS pipeline. "
            "All data is local — no external network calls."
        )

        with gr.Tabs():
            # Tab 1 — Run Pipeline
            with gr.Tab("▶ Run Pipeline"):
                gr.Markdown("## Run the full end-to-end pipeline")
                gr.Markdown(
                    "Equivalent to `dsfs-run`. Select a config, click **Run**, "
                    "and watch the log stream. The manifest JSON appears when the run finishes."
                )
                with gr.Row():
                    cfg_dd = gr.Dropdown(
                        choices=_configs(),
                        label="Run config",
                        value=_configs()[0] if _configs() else None,
                        allow_custom_value=True,
                    )
                    run_btn = gr.Button("▶ Run Pipeline", variant="primary", scale=0)

                log_tb = gr.Textbox(label="Log", lines=16, interactive=False)
                manifest_json = gr.JSON(label="Manifest")

                run_btn.click(
                    fn=run_pipeline,
                    inputs=[cfg_dd],
                    outputs=[log_tb, manifest_json],
                )

            make_forecast_tab()
            make_extraction_tab()
            make_drift_tab()
            make_lineage_tab()

        gr.Markdown(
            "_This POC demonstrates pipeline mechanics on synthetic data. "
            "Schema conformance ≠ extraction accuracy. "
            "See `docs/17-poc-findings.md` for the mandatory reporting caveat._"
        )

    return demo


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:  # pragma: no cover
    demo = build_app()
    demo.launch(server_name="127.0.0.1", share=False)


if __name__ == "__main__":
    main()
