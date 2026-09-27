# 12 — Implementation Milestones

Adapted directly from the Developer Handoff's own milestone list (Section 18), reconciled with the offline/local-only constraint. Each milestone lists objective, inputs/outputs, components affected, dependencies, tests, and acceptance criteria per the handoff's requested output format (Section 20). This documentation package (docs 00–14 + schemas) **is Milestone 0**; it is complete as of this writing.

---

## Verified implementation status — 2026-09-27

| Milestone | Status | Evidence / remaining work |
|---|---|---|
| 0 | Complete | Numbered designs and canonical schemas present; status reconciled with code. |
| 1 | Complete for source-checkout workflow | Missing models restored; contract validation and UTC handling tested. Dependency snapshot recorded. Fresh editable installation still needs verification where build tooling is available. |
| 2 | Complete at POC default scale | 4,160 D0 rows and 675 D1 notes; deterministic source IDs, notes, and demand; no rendered-text dependency in demand realization. Entity-paraphrase and 5 seeded D4 drift scenarios added (`--paraphrase-entities`, `--drift-scenario`). |
| 3 | Rules baseline verified; hybrid stages deferred | Regex + supplied-mention matching, schema validation, persisted quarantine, immutable revision IDs, conservative reversal linking, historical status reconstruction. Statistical NER/local LLM remain unimplemented. |
| 4 | Evaluation machinery implemented; independent-review scaffold added, labeling pending | 40 provisional development cases, annotation/split validation, metric tests, diagnostics, and reproducible reports. `scripts/select_review_sample.py` + `docs/annotations/human_review_instructions.md` add an independent 50-note review scaffold (reuses existing M4 machinery, no new scoring code) — labeling itself is a manual task, status in `19-remaining-implementation.md`. |
| 5 | Complete | PIT-correct feature transformation: weekly cutoffs, 28-day horizon, 30/90-day lookbacks, direction/magnitude/conflict/staleness aggregation, schema-validated output. **`build_d3` referenced a nonexistent `week_start` column and had never worked on real generated data — fixed 2026-09-27.** |
| 6 | Complete | Feature access layer: `FeatureStore` with `get_features()` / `get_historical_features()`, `load_feature_store()` from persisted ledger + notes, CLI entry point `dsfs-features`. Raw text never returned. |
| 7 | Complete | Rolling-origin forecast baseline (arm A): Ridge regression with lag/seasonal/rolling features, pure numpy (no sklearn). Frozen ForecastConfig enforces identical model config across arms. Direct multi-horizon (one ridge head per horizon) replaces the earlier one-step-reused-for-every-horizon bug. |
| 8 | Complete | Enhanced arms B (oracle ground-truth features), C (extracted-signal features), D (shuffled control). Decision logic from docs/08 applied, restructured to always show all branches. **A `forecast_cutoff` dtype mismatch (ISO string vs. `datetime.date`) meant arms B/C/D silently received zero merged signal features on every real run before 2026-09-27 — any forecast report from before that date is invalid.** |
| 9 | Complete at POC scope | Ablation matrix (5 of 9 docs/08 rows; 4 explicitly documented as not implemented, not fabricated), bootstrap CI, paired-permutation test, per-horizon and signal-exposed-subset segmentation. `dsfs-forecast --ablation full`. |
| 10 | Complete at POC scope | Lineage tracing (feature → signal → evidence), extraction-latency freshness measurement, 5 of 7 docs/10 drift scenarios, pure-numpy KS/chi-square detectors, no-drift-window calibration, persistence-based alerting, per-scenario drift report. `dsfs-lineage`, `dsfs-drift-report`. |
| 11 | Complete | `dsfs-run` orchestrates synth → extraction → evaluation → features → forecast(+ablation) → drift → lineage in one command, producing a manifest with per-artifact and code SHA-256. End-to-end smoke test against real generated data. |
| 12 | Complete | `17-poc-findings.md` (from a real full-scale `dsfs-run`; decision-logic branch fired is B ≈ A) and `18-production-gap.md`, both populated from actual run output, not invented numbers. |

Verification: **296 passing tests** on Windows/Python 3.14.4 (up from 181 at the
start of the M9-M11 implementation pass). The default generator-to-ledger smoke
run accepted 675/675 schema-valid records. Tests cover calendar boundaries,
later cancellation availability, ambiguous targets, distinct re-extraction IDs,
idempotent ledger retries, and rejected-record persistence. This does not
establish the original hybrid pipeline's accuracy.

Milestone 4 adds 31 tests covering hand-built confusion sets, missing/duplicate
outputs, abstention, citation grounding, temporal overlap, provenance/split
checks, report reproducibility, and gold-mode rejection of draft labels.
The provisional starter yields actionable-event macro-F1 0.4158; this is a
development diagnostic, not a held-out human-gold result. See docs/15 for the
review workflow and remaining data dependency.

Milestones 5–6 add 39 tests covering PIT eligibility (available_at <= cutoff,
future-effective inclusion, superseded exclusion), window boundaries (30-day
lookback, 90-day delay lookback), feature aggregation (direction votes, negation,
magnitude, cancellations, conflicts, staleness), schema conformance, batch
retrieval, DataFrame output, and the adversarial leakage test from docs/11.

Milestones 7–8 add 20 tests covering rolling-origin correctness (no future
leakage in training), config identity (frozen config shared across all arms),
metric computations (MASE, MAE, bias, incremental lift), shuffled control
(entity-time alignment broken, reproducible, lineage cleared), and arm
comparison. **Note:** the original "B/C/D predictions differ from A" claim was
only ever exercised against a hand-built test fixture where both sides of a
date comparison happened to be `pd.Timestamp`; on real generated data the
comparison silently failed and arms B/C/D were identical to A until the
2026-09-27 fix (see Milestone 8 row above and `13-risks-and-dependencies.md`).

Milestones 9-11 add 65 tests: ablation matrix and masking correctness,
bootstrap/permutation statistics, segmentation, lineage round-trip against real
extraction output, freshness distributions, 5 seeded drift scenarios, KS/chi-square
detectors, no-drift-window calibration, persistence-based alerting, and a
full end-to-end smoke test.

Next: Milestone 12 findings report and production-gap assessment — see
`17-poc-findings.md`, `18-production-gap.md`, and `19-remaining-implementation.md`.

### Milestone 0 — Research-to-development validation (this package)

- **Objective:** confirm requirements, architecture, schemas, interfaces, assumptions, and blockers before any code exists.
- **Inputs:** the five source research documents; project owner's offline/local-only constraint.
- **Outputs:** `docs/00`–`14`, `docs/schemas/*.json` (this package).
- **Components affected:** none yet (documentation only).
- **Dependencies:** none.
- **Tests:** manual cross-check — every `CONFIRMED` item traces to a source document; the three JSON Schema files validate against a hand-built example record each.
- **Acceptance criteria:** all 28 handoff questions answered or marked OPEN with an owner; no silent invention of thresholds or requirements.
- **Risks:** stakeholder review may surface a disagreement with a reconciliation call — tracked in `13-risks-and-dependencies.md`.
- **POC vs. production:** N/A (docs only).

### Milestone 1 — POC foundation

- **Objective:** repository structure, configuration, reproducibility scaffolding, core contract loading, dev environment.
- **Inputs:** this docs package.
- **Outputs:** repo skeleton (`src/`, `tests/`, `data/` [gitignored raw/interim/processed], `configs/`), a config-loading module, the three JSON Schemas wired into Pydantic models, a `pyproject.toml`/`requirements.txt` pinned to offline-installable packages.
- **Components affected:** all (foundation).
- **Dependencies:** Milestone 0.
- **Tests:** contract round-trip test (build a Pydantic object → dump → validate against JSON Schema → parse back).
- **Acceptance criteria:** `pytest` runs green on an empty-but-wired repo; schema validation demonstrably rejects a malformed record.
- **Risks:** environment-specific dependency/build tooling; the tested snapshot is not a cross-platform lock.

> **Scope note:** the entries below retain the original objectives and acceptance criteria. The verified status table above records what is implemented and which planned capabilities remain deferred.

### Milestone 2 — Synthetic dataset

- **Objective:** generate D0 (tabular demand history) and D1 (synthetic notes) using the causal generation order from `06-synthetic-data-design.md`.
- **Inputs:** entity/product cardinality and scenario-template parameters (to be chosen as engineering defaults, documented in the generator's own config).
- **Outputs:** D0 table; D1 note corpus with generator-internal ground truth kept separate from rendered text.
- **Components affected:** synthetic data generator.
- **Dependencies:** Milestone 1.
- **Tests:** a leakage test asserting the demand-realization function's code path never reads rendered note text or extracted signals; a distributional sanity check on D0 (no negative demand, plausible seasonality).
- **Acceptance criteria:** D0/D1 written to local storage; causal-ordering assertion test passes.
- **Risks:** generator complexity creeping toward "too easy to extract" or "too easy to forecast" — mitigated by D5's adversarial notes and arm D's negative control.

### Milestone 3 — Extraction pipeline

- **Objective:** implement rules → NER → local LLM (or degraded rules+NER) → validator, per `07-extraction-pipeline-design.md`.
- **Inputs:** D1.
- **Outputs:** `SignalRecord` rows in the ledger.
- **Components affected:** extraction pipeline, signal ledger.
- **Dependencies:** Milestones 1–2; the local LLM/runtime feasibility check from `05-technology-decision-matrix.md`.
- **Tests:** the five hand-authored hard cases from `11-testing-strategy.md`; schema-conformance test.
- **Acceptance criteria:** ≥99.5% schema-conformant output (PROPOSED gate); all five hard cases produce the documented expected interpretation.
- **Risks:** local model infeasibility — triggers the documented degradation path, not a silent quality drop.

### Milestone 4 — Extraction evaluation

**Current status:** engineering implemented; independent D2 annotation and
held-out validation pending. The provisional report populates the required
metrics without representing assistant-drafted labels as human gold.

- **Objective:** measure extraction performance against D2, independent of forecasting.
- **Inputs:** D2, the extraction pipeline's output on D2's source notes.
- **Outputs:** the extraction metrics report from `09-evaluation-plan.md`, including the error taxonomy breakdown.
- **Components affected:** evaluation module.
- **Dependencies:** Milestones 2–3, D2 annotation completed.
- **Tests:** metric-computation unit tests against a hand-built confusion set.
- **Acceptance criteria:** report produced with macro-F1, field-level accuracy, unsupported-inference rate, and abstention precision/recall all populated.
- **Risks:** D2 annotation effort underestimated — track in `13-risks-and-dependencies.md`.

### Milestone 5 — Signal-to-feature transformation

- **Objective:** convert `ACTIVE`, validated signals into point-in-time-correct `ForecastFeatureRecord` rows.
- **Inputs:** signal ledger, D0's forecast cutoffs.
- **Outputs:** D3 (point-in-time feature dataset).
- **Components affected:** feature transformation.
- **Dependencies:** Milestone 3.
- **Tests:** the PIT eligibility test and the "future-effective but available-in-time" inclusion test from `11-testing-strategy.md`.
- **Acceptance criteria:** zero PIT violations across the full D3 build.
- **Risks:** the highest-consequence bug class in the whole project — extra test coverage here is justified.

### Milestone 6 — Feature access layer

- **Objective:** implement `get_features`/`get_historical_features`, per `04-api-data-contracts.md`.
- **Inputs:** D3.
- **Outputs:** a callable, tested Python interface (optional localhost HTTP wrapper if pursued).
- **Components affected:** feature access layer.
- **Dependencies:** Milestone 5.
- **Tests:** contract tests (argument validation, versioning, batch size handling).
- **Acceptance criteria:** the forecasting harness can retrieve a feature batch for an arbitrary set of (entity, cutoff) pairs and get back schema-valid rows with lineage metadata attached.
- **Risks:** none material — this is a thin layer by design.

### Milestone 7 — Forecast baseline

- **Objective:** implement arm A (tabular-only) forecast.
- **Inputs:** D0.
- **Outputs:** baseline forecast results, frozen model config.
- **Components affected:** forecast harness.
- **Dependencies:** Milestone 2.
- **Tests:** rolling-origin CV correctness (no future observation enters any training window).
- **Acceptance criteria:** reproducible baseline MASE/MAE reported.
- **Risks:** none material.

### Milestone 8 — Enhanced forecast (arms B, C, D)

- **Objective:** implement oracle, extracted, and shuffled-control arms with identical model/config to arm A.
- **Inputs:** D3, Milestone 7's frozen baseline config.
- **Outputs:** results for arms B/C/D.
- **Components affected:** forecast harness.
- **Dependencies:** Milestones 5–7.
- **Tests:** config-identity assertion (arms A–D differ only in feature input, verified programmatically, not just by inspection).
- **Acceptance criteria:** all four arms run under the exact same rolling-origin schedule.
- **Risks:** accidental confound (e.g. different random seed) — guarded by the config-identity test.

### Milestone 9 — Controlled evaluation and ablations

- **Objective:** run the full ablation matrix from `08-forecasting-experiment-design.md`, apply the decision logic (B≈A / B>A,C≈A / etc.).
- **Inputs:** Milestone 8 outputs.
- **Outputs:** the evaluation report per `09-evaluation-plan.md`, including per-arm, per-horizon, per-segment, and signal-exposed-subset breakdowns.
- **Components affected:** evaluation module.
- **Dependencies:** Milestone 8.
- **Tests:** statistical computation tests (bootstrap CI, paired-difference distribution).
- **Acceptance criteria:** report explicitly states which branch of the decision logic the results fall into.
- **Risks:** ambiguous results (e.g. B only marginally > A) — documented as inconclusive rather than forced into a positive/negative label.

### Milestone 10 — Lineage, freshness, and drift

- **Objective:** demonstrate lineage-trace (feature → signal → evidence), freshness measurement, and the drift plan from `10-drift-monitoring-plan.md` against D4.
- **Inputs:** D4, the full pipeline from Milestones 2–6.
- **Outputs:** lineage-trace utility + demonstration; freshness report; drift-detection report (detection rate, false-alert rate, lead time per scenario).
- **Components affected:** lineage utility, drift module.
- **Dependencies:** Milestones 3–6.
- **Tests:** lineage-trace correctness test (given a feature row, resolve back to the exact source note); drift-calibration false-alert-rate test on no-drift control windows.
- **Acceptance criteria:** every feature row in a sample resolves to a complete provenance chain; drift report includes both detection lead time and calibrated false-alert rate, never one without the other.
- **Risks:** none material beyond the general drift caveats in `10-drift-monitoring-plan.md`.

### Milestone 11 — End-to-end POC

- **Objective:** run the complete pipeline once, start to finish, on a fresh dataset, producing the full report bundle.
- **Inputs:** all prior milestones' code, fresh D0–D6 generation.
- **Outputs:** a single end-to-end run artifact (report + all intermediate tables), demonstrating the full hypothesis chain from source note through forecast evaluation.
- **Components affected:** all.
- **Dependencies:** Milestones 1–10.
- **Tests:** the end-to-end test family from `11-testing-strategy.md`.
- **Acceptance criteria:** the run completes without manual intervention and produces every artifact listed in `00-development-requirements-spec.md` Q6.
- **Risks:** integration issues between components built/tested in isolation — this milestone exists specifically to surface them.

### Milestone 12 — POC findings and production-gap assessment

- **Objective:** document what worked, what failed, what remains uncertain, and what would change for production.
- **Inputs:** Milestone 11's full results.
- **Outputs:** a findings report (extends `13-risks-and-dependencies.md` and `14-open-questions.md` with actual results) and an updated production-gap section referencing `01-poc-scope-and-non-goals.md`.
- **Components affected:** none (reporting only).
- **Dependencies:** Milestone 11.
- **Tests:** N/A.
- **Acceptance criteria:** the mandatory reporting caveat from `09-evaluation-plan.md` is present verbatim; every non-goal from `01-poc-scope-and-non-goals.md` is either still excluded or explicitly justified as newly in-scope.
- **Risks:** temptation to overstate synthetic results as real-world validation — explicitly guarded against by the caveat requirement.
