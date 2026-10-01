# Demand Signal Feature Service — POC

An offline, local-only proof of concept testing whether qualitative business
notes can be turned into point-in-time-correct demand-signal features that
measurably improve a forecast versus a tabular-only baseline. See
`docs/00-development-requirements-spec.md` for the full requirements
reconciliation, and `docs/12-implementation-milestones.md` for the build
sequence.

**Everything in this repo runs locally, offline. No hosted LLM APIs, no
cloud storage, no external services.**

## Status

- **Milestone 0** (documentation package) — complete; updated to distinguish the
  implemented baseline from the proposed hybrid architecture.
- **Milestone 1** (foundation) — restored and verified. Typed Pydantic models,
  canonical JSON Schema validation (including timestamp formats), UTC timestamp
  normalization, configuration, and contract tests are present. Python source
  under `src/dsfs/models/` is no longer excluded by the model-weight ignore rule.
- **Milestone 2** (synthetic dataset) — implemented and verified. Seeded demand,
  notes, source IDs, and separate generator ground truth are reproducible.
  Default run: 40 entities, 104 weeks, 4,160 demand rows, 675 notes.
- **Milestone 3** (extraction) — verified **rules baseline**. Regex semantics and
  exact matching of supplied entity mentions; statistical NER and the local LLM
  are not implemented. Includes distinct physical revision IDs, append-only
  storage with idempotent retries, persisted rejected records, conservative
  reversal linking, and a historical ledger view that preserves earlier state.
  Ambiguous reversals stay `REVIEW`; they never silently retire a guessed claim.
- **Milestone 4** (extraction evaluation) — evaluation machinery implemented:
  annotation contract, split checks, field/event/abstention/grounding metrics,
  diagnostics, and reproducible report bundles. Includes 40 **provisional**
  development challenge notes. Human adjudication and held-out D2 evaluation
  remain pending; see `docs/15-extraction-evaluation-workflow.md`.
- **Milestone 5** (signal-to-feature transformation) — implemented. PIT-correct
  feature building with weekly UTC cutoffs and 28-day horizons. Eligible signals
  are filtered by available_at <= cutoff, effective-period/horizon intersection,
  and ACTIVE record status. Percentages stay separate from quantities. 30-day
  lookback for presence/direction/recency; 90-day lookback for delay counts.
  Every feature row passes the forecast_feature JSON Schema contract.
- **Milestone 6** (feature access layer) — implemented. `FeatureStore` provides
  `get_features()` (batch point-in-time retrieval) and `get_historical_features()`
  (DataFrame for the forecasting experiment harness). Raw note text is never
  returned. `load_feature_store()` loads from persisted ledger + notes for a
  specific extraction run. CLI via `dsfs-features --run-id <extraction_run_id>`.
- **Milestone 7** (forecast baseline) — implemented. Arm A: rolling-origin CV
  with Ridge regression using lag, seasonal, and rolling-window features. Pure
  numpy implementation (no sklearn/scipy dependency). Frozen `ForecastConfig`
  ensures identical model config across all arms.
- **Milestone 8** (enhanced forecast arms) — implemented. Arm B: oracle features
  from generator ground truth. Arm C: extracted-signal features via the feature
  access layer. Arm D: shuffled control (entity-time alignment broken, seeded).
  Decision logic from docs/08 applied automatically. Mandatory reporting caveat
  included. CLI via `dsfs-forecast --run-id <extraction_run_id>`.
- **Milestone 9** (controlled evaluation and ablations) — implemented at POC
  scope. Ablation matrix (5 of 9 docs/08 rows; 4 documented as not implemented,
  never fabricated), bootstrap CI, paired-permutation test, per-horizon and
  signal-exposed-subset segmentation. `dsfs-forecast --ablation full`.
- **Milestone 10** (lineage, freshness, drift) — implemented at POC scope.
  Feature→signal→evidence lineage tracing, extraction-latency freshness,
  5 of 7 docs/10 seeded drift scenarios, pure-numpy KS/chi-square detectors,
  no-drift-window calibration, persistence-based alerting. `dsfs-lineage`,
  `dsfs-drift-report`.
- **Milestone 11** (end-to-end POC) — implemented. `dsfs-run` chains every
  stage into one command producing a manifest with per-artifact and code
  SHA-256 hashes.
- **Milestone 12** (findings and production gap) — complete. `docs/17-poc-findings.md`
  documents all Gate A–I results (real numbers, no fabricated figures), the
  mandatory reporting caveat verbatim, and the B≈A decision-logic branch that
  fired. `docs/18-production-gap.md` assesses every non-goal and priority-orders
  the seven production gaps. 18 acceptance tests in `tests/test_m12_acceptance.py`
  verify the caveat is present verbatim and every non-goal from `docs/01` is
  explicitly addressed.

**Two critical bugs were found and fixed while implementing M9-M11** — both
made prior forecast results on real (non-fixture) data meaningless: a
`forecast_cutoff` dtype mismatch meant arms B/C/D never actually received
merged signal features (numerically identical to arm A), and `build_d3`
referenced a column name (`week_start`) that never existed in real D0 output.
See `docs/13-risks-and-dependencies.md` for the full list.

Verification on Windows / Python 3.13.14: **314 tests passed** (up from 296).
A default D0/D1 → extraction run accepted all 675 records with zero schema
rejections. This is **schema conformance, not extraction accuracy**. The
vocabulary is still close to the generator templates; meaningful semantic
scores require held-out, independently adjudicated D2 labels. See
`docs/07-extraction-pipeline-design.md` for the baseline limitations and
`docs/12-implementation-milestones.md` for remaining acceptance work.

## Layout

```text
docs/                         Numbered requirements/designs and canonical schemas
src/dsfs/
  config.py, contracts.py      Local settings and wire-contract validation
  models/                     Evidence, signal, and forecast-feature models
  synth/                      Latent state, notes, demand, and dataset writer
  extraction/                 Rules, entity matching, reconciliation, ledger
  evaluation/                 D2 contracts, metrics, runner, report writer
  features/                   PIT feature transformer, access layer, D3 builder
  forecast/                   4-arm experiment harness, oracle, shuffle, report
tests/                        Component and evaluation regression tests
data/annotations/             Versioned, reviewable D2 labels (tracked)
data/{raw,interim,processed}/  Generated local artifacts (gitignored)
reports/                      Generated evaluation/drift reports
```

## Setup and verification

Run commands from the directory containing this README and `pyproject.toml`.
Python 3.11+ is declared; the tested dependency snapshot is for Python 3.14.4
on Windows. Use a local virtual environment and an editable source install
(the canonical schemas remain in this checkout's `docs/schemas/`).

```bash
python -m pip install -r requirements.txt
python -m pytest -q
python -m dsfs.synth.generator
python -m dsfs.extraction.pipeline
python -m dsfs.evaluation.pipeline
python -m dsfs.features.pipeline --run-id <extraction_run_id>
python -m dsfs.forecast.pipeline --run-id <extraction_run_id> --ablation full
python -m dsfs.lineage --run-id <extraction_run_id>
python -m dsfs.orchestrate --config configs/e2e_smoke.json
```

`dsfs.orchestrate` (console script `dsfs-run`) chains every stage above into
one command and writes `reports/manifest.json` with per-artifact and code
SHA-256 hashes. Use `configs/e2e_full.json` for the default POC scale (40
entities, 104 weeks) or `configs/e2e_smoke.json` for a fast (~15s) sanity check.

`requirements.txt` installs the package itself and current runtime/test
requirements. Optional `ner`, `local-llm`, `forecast`, and `tables` extras in
`pyproject.toml` are future-stage dependencies; installing them does not enable
unimplemented stages. The LLM flag raises explicitly if enabled.

For the exact tested runtime/test versions, add
`-c requirements-tested.txt` to the install command. This is a Windows/Python
3.14 dependency snapshot, not a portable lock or a bundled installer. Package
and build-tool wheels (`setuptools>=68`) must already be locally available for
an offline install, e.g. use `--no-index --find-links <local-wheelhouse>`.
No pipeline command downloads packages, models, or external data.

If dependencies are already installed and an editable install is unavailable,
PowerShell can run this checkout with `$env:PYTHONPATH = (Join-Path $PWD 'src')`.
This source-path mode was used for the verification above; a fresh editable
installation has not been verified in this environment (setuptools is absent).

Normal extraction creates a new run ID and processing timestamp. To reproduce
an identical signal snapshot, pass the same `extraction_run_id` and
`extracted_at` to `run_extraction`. Select one run explicitly when querying
`ledger_as_of`; different extractor runs are alternative interpretations of
one corpus, not additional business events. Historical replay uses source
`available_at`, while `extracted_at` records the actual batch-processing time.

Evaluation writes a frozen input snapshot, predictions, quarantine and JSON/
Markdown results under `reports/extraction/`. The starter is explicitly
provisional: its actionable-event macro-F1 is 0.4158 despite 100% schema-valid
output. It is not human gold or a blind holdout. See docs/15 for metric
definitions, reviewer metadata, and the `--require-gold` gate.

## Key documents to read first

1. `docs/00-development-requirements-spec.md` — what/why, reconciled from five prior research passes.
2. `docs/03-data-model.md` — the three-layer data model and the point-in-time eligibility rule (the single most important correctness constraint in the project).
3. `docs/08-forecasting-experiment-design.md` — the 4-arm experiment that answers the actual business hypothesis.
4. `docs/17-poc-findings.md` — what the POC actually found, from a real full-scale run.
5. `docs/18-production-gap.md` — what's missing before any production claim.
6. `docs/14-open-questions.md` — what's still unresolved and who resolves it.
