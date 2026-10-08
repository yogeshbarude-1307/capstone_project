# CLAUDE.md — Demand Signal Feature Service (DSFS)

## Project Overview

**DSFS** is a local Python proof-of-concept that evaluates whether early qualitative account notes (e.g., CRM entries) can improve weekly customer demand forecasts. It is a capstone project demonstrating an end-to-end ML pipeline — from synthetic data generation through feature extraction, experiment, evaluation, and drift monitoring — entirely offline with no cloud APIs.

**Key honest result:** In the frozen study (seeds 101–105, 40 accounts × 104 weeks, 39,200 paired outcomes per arm), both the oracle arm (B) and the extracted-signal arm (C) were *worse* than the tabular baseline (A). This is a genuine negative result, documented openly. The recommendation is to fix the feature representation before adding NER/LLM capability.

---

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -c requirements-tested.txt
.\.venv\Scripts\python.exe -m pytest -q
```

**Platform:** Windows 11, Python ≥ 3.11 (tested on 3.14.7). Use PowerShell.

---

## Run Commands

| Command | Description |
|---|---|
| `dsfs-run --config configs/e2e_smoke.json` | Quick smoke run (HTTP-backed) |
| `dsfs-run --config configs/e2e_full.json` | Full 40-account / 104-week pipeline run |
| `dsfs-study` | Full frozen multi-seed study (dev seeds 1–3, eval seeds 101–105) |
| `dsfs-server` | Launch dashboard at http://127.0.0.1:8000 |
| `dsfs-generate` | Synthetic data generation only |
| `dsfs-extract` | Extraction pipeline only |
| `dsfs-evaluate` | Evaluation metrics only |
| `dsfs-forecast` | Forecasting experiment only |

---

## Architecture

```
Synthetic Data Generator
  ├── Source Evidence Store (immutable raw notes)
  └── D0: Tabular demand history (baseline)
        │
        ▼
  Extraction Pipeline (rules → NER stub → validator → abstention)
        │
        ▼
  Signal Ledger (append-only, versioned, with provenance)
        │
        ▼
  Feature Transformation (point-in-time windowed/decayed signals)
        │
        ▼
  Feature Access Layer (localhost HTTP serving, batch + historical)
        │
        ▼
  Forecasting Experiment Harness — 4 arms, rolling-origin CV:
    A: tabular baseline
    B: oracle signal (ground truth features)
    C: extracted signal
    D: shuffled signal (negative control)
        │
        ▼
  Evaluation & Reporting (extraction metrics, forecast lift, drift, lineage)
```

---

## Package Structure

```
src/dsfs/
├── synth/          Synthetic data generation (causal latent state → notes → demand)
├── extraction/     Rules-based extractor, signal ledger, entity resolution
├── features/       DemandFeatureService, point-in-time feature serving, HTTP provider
├── forecast/       4-arm experiment harness (Ridge regression, rolling-origin CV)
├── evaluation/     Extraction metrics, ablations, bootstrap CI, review package builder
├── drift/          Statistical drift detection, alerting, calibration
├── models/         Pydantic data models (SignalRecord, DemandFeatureRecord, etc.)
├── config.py       Pydantic-settings Settings; env prefix DSFS_
├── contracts.py    JSON Schema validation for all wire contracts
├── orchestrate.py  End-to-end pipeline orchestrator (dsfs-run)
├── server.py       FastAPI dashboard backend (dsfs-server)
├── study.py        Multi-seed frozen study with bootstrap CI (dsfs-study)
├── lineage.py      Demand feature → signal → source-text lineage tracing
└── freshness.py    Publication latency measurement vs. 60-minute target
```

---

## Key Design Decisions

- **Fully offline / local-only.** No hosted LLM APIs, no cloud services, no real company data. `DSFS_LLM_EXTRACTION_ENABLED` is `false` by default; the LLM stage raises `NotImplementedError`.
- **Causal separation.** The synthetic generator uses three independent RNG streams. Latent events drive demand independently of note rendering — notes never leak hidden state.
- **Abstention over guessing.** The extractor abstains when evidence is insufficient rather than producing a low-confidence extraction.
- **Append-only Signal Ledger.** All extracted signals are immutable once written; point-in-time views (`ledger_as_of()`) prevent look-ahead bias.
- **Point-in-time feature serving.** Features are served via localhost HTTP (`HttpFeatureProvider`) — the forecaster never sees future signals.
- **Acceptance contract.** `docs/20-realignment-acceptance.md` is the authoritative spec. It supersedes any conflicting claims in `docs/00–19`.

---

## Data Contracts (JSON Schemas)

Located in `docs/schemas/`:

| Schema | Description |
|---|---|
| `source_evidence.schema.json` | Raw immutable note + metadata |
| `signal_record.schema.json` | Extracted structured signal with provenance |
| `forecast_feature.schema.json` | Features fed into forecasting arms |
| `demand_feature.schema.json` | Combined demand feature row (D3) served to forecaster |

Validation is enforced by `src/dsfs/contracts.py`. Invalid records are quarantined, not silently dropped.

---

## Environment Variables

All settings use the `DSFS_` prefix and can be overridden via a `.env` file:

| Variable | Default | Description |
|---|---|---|
| `DSFS_DATA_RAW_DIR` | `data/raw` | Raw data directory |
| `DSFS_DATA_INTERIM_DIR` | `data/interim` | Interim data directory |
| `DSFS_DATA_PROCESSED_DIR` | `data/processed` | Processed data directory |
| `DSFS_SCHEMA_DIR` | `docs/schemas` | JSON Schema directory |
| `DSFS_REPORTS_DIR` | `reports` | Run artifact output directory |
| `DSFS_LLM_EXTRACTION_ENABLED` | `false` | Enable LLM extraction stage (stub only) |
| `DSFS_LOCAL_LLM_MODEL_PATH` | — | Path to local LLM model weights |

---

## Testing

```powershell
# Run all 337 tests
.\.venv\Scripts\python.exe -m pytest -q

# Run by module
.\.venv\Scripts\python.exe -m pytest tests/extraction/ -v
.\.venv\Scripts\python.exe -m pytest tests/forecast/ -v
.\.venv\Scripts\python.exe -m pytest tests/drift/ -v
```

Tests are organized by subpackage under `tests/`. Key acceptance tests:
- `tests/test_realignment.py` — temporal / serving semantics acceptance
- `tests/test_m12_acceptance.py` — milestone 12 acceptance gates
- `tests/extraction/test_entity_resolution_paraphrase.py` — documents 0% recall with aggressive paraphrase (known limitation)

No mocking of the feature service: tests use the real `InProcessFeatureProvider` or `HttpFeatureProvider` to catch mock/prod divergence.

---

## Current Status & Known Limitations

| Area | Status |
|---|---|
| Synthetic data generation | Complete |
| Rules-based extraction | Complete (version `rules-v0.3.0`) |
| NER / LLM extraction stage | Deferred — raises `NotImplementedError` |
| Entity resolution (paraphrase) | 0% recall with aggressive paraphrase (Gap 2) |
| Signal Ledger + Feature Service | Complete |
| 4-arm experiment harness | Complete |
| Drift monitoring | Complete (14-week lead, 30% false-alert rate) |
| Human annotation review | Pending (Gap 3) |
| Forecast lift (B and C vs. A) | Negative result — arms B and C worse than baseline |

See `docs/18-production-gap.md` for the full priority-ordered gap list and `docs/21-realignment-findings.md` for frozen study results.

---

## Key Documentation

| Doc | Purpose |
|---|---|
| `docs/20-realignment-acceptance.md` | **Authoritative acceptance contract** (supersedes docs/00–19) |
| `docs/21-realignment-findings.md` | Frozen study results (current) |
| `docs/02-architecture.md` | End-to-end architecture diagram |
| `docs/17-poc-findings.md` | Historical POC results |
| `docs/18-production-gap.md` | Priority-ordered production gaps |
| `docs/22-vp-demo-guide.md` | 5-minute dashboard presentation guide |
| `design-qa.md` | Dashboard visual QA pass results |
