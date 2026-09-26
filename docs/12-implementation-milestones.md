# 12 — Implementation Milestones

Adapted directly from the Developer Handoff's own milestone list (Section 18), reconciled with the offline/local-only constraint. Each milestone lists objective, inputs/outputs, components affected, dependencies, tests, and acceptance criteria per the handoff's requested output format (Section 20). This documentation package (docs 00–14 + schemas) **is Milestone 0**; it is complete as of this writing.

---

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
- **Risks:** none — this milestone is currently OUT OF SCOPE for this documentation-only effort (see below).

> **Scope note:** per your decision to produce documentation only in this pass, Milestones 1–12 below are **planned, not started**. They are included so the next work session has an unambiguous, testable sequence to execute against.

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
