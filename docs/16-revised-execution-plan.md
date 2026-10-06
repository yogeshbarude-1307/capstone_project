> Historical design/evidence: the [realignment acceptance contract](20-realignment-acceptance.md) supersedes conflicting scope and semantics below. The current target is weekly customer demand, Monday UTC cutoffs, four separate weekly horizons, PASS-only published signals, required HTTP consumption, a one-hour simulated freshness target, and matched forecast-degradation lead time. Earlier test counts and results require revalidation.

# 16 — Revised Execution Plan (Track A fixes + M9–M12)

Written 2026-09-27. Supersedes the "next batch" note in [12-implementation-milestones.md](12-implementation-milestones.md) and organizes M9–M12 around the business gates from the Phase One research report rather than around milestone numbers alone.

## Framing

The Phase One research report reframes the POC as a chain of falsifiable gates:

```
A signal exists → B available early → C extractable → D entity-aligned →
E validated → F predictive → G exploitable → H business-impactful → I operable
```

This POC can only address **Gates C, D, E, F, G, I under synthetic conditions**. Gates A, B, and H require real company notes, real timestamps, and real decision-cost data respectively; they remain explicit production-gap items.

Success is reported along four independent layers, per the research:

| Layer | Gates | Where addressed |
|---|---|---|
| Signal validity | A, B | Planted by synthetic generator; not measured. Deferred to production. |
| Extraction validity | C, D, E | Track A fixes + independent-review sample + entity-paraphrase stress test |
| Forecast value | F, G | M9 ablation matrix + segmentation |
| Operational value | I | M10 lineage, freshness, drift |

The dev team's deviations from the original design have been reviewed against this outcome and judged as follows:

| Deviation | Verdict | Rationale |
|---|---|---|
| Rules-only extraction (NER/LLM stubs) | Acceptable | Research cautions against LLM-first; simpler ensembles often win. |
| Provisional self-scored D2 | Not acceptable — mitigate in Layer 2 | Extraction validity is an independent success layer; self-scoring collapses it. |
| Entity resolution = exact string match | Not acceptable — mitigate in Layer 2 | Research: entity resolution may matter more than extraction itself. |
| Single-entity note assumption in oracle | Fix (Track A) | Symptom of the same under-modeling. |

---

## Track A — Flaw fixes

Bundle into ~2 PRs. Correctness first, cleanups next.

### A1 — Correctness

| # | File | Fix | Test |
|---|---|---|---|
| 1 | [features/pipeline.py:30](../src/dsfs/features/pipeline.py) | Return type `-> Path` → `-> tuple[Path, int, int]`; update callers. | `test_build_d3_returns_tuple`. |
| 2 | [features/pipeline.py:74](../src/dsfs/features/pipeline.py) | Replace bare `except Exception` with typed catch on `ValidationError`; log row index + error; drop `.dropna()` before validation. | Invalid-row test asserts quarantine counted and logged. |
| 3 | [forecast/harness.py:191](../src/dsfs/forecast/harness.py) | `ForecastConfig` validator asserts `lag_weeks == sorted(lag_weeks)` and all positive. | Unsorted `lag_weeks` raises. |
| 4 | [extraction/reconciliation.py:24](../src/dsfs/extraction/reconciliation.py) | Guard: empty `abstention_reason` treated as no-allowed-reason. | Reversal with unset reason blocked cleanly. |
| 5 | [evaluation/annotations.py:55](../src/dsfs/evaluation/annotations.py) | Change `effective_end > effective_start` to `>=` to match [signal_record.py](../src/dsfs/models/signal_record.py). | Zero-length interval passes annotation validation. |
| 6 | [forecast/pipeline.py:142-150](../src/dsfs/forecast/pipeline.py) | Restructure decision block: always evaluate B-vs-A, C-vs-A, C-vs-B, D-lift; leakage warning appended, not exclusive. | D-lift positive still prints B/C branches. |
| 7 | [forecast/oracle.py:61-63](../src/dsfs/forecast/oracle.py) | Iterate over `mentions` instead of `[0]`. | Two-entity note produces oracle rows for both. |

### A2 — Multi-horizon ridge

[forecast/harness.py:217-218](../src/dsfs/forecast/harness.py) currently applies a one-step model H times to the same feature vector. M9's per-horizon breakdown requires meaningful multi-step forecasts. **Implement direct multi-horizon**: train H separate ridge heads, one per horizon, each on `y_{t+h}`. ~30 LoC.

### A3 — Cleanups (batched)

- Remove dead `_weekly_cutoffs` in [features/pipeline.py:25-27](../src/dsfs/features/pipeline.py).
- Extract shared `direction_vote` used by [transformer.py](../src/dsfs/features/transformer.py) and [oracle.py](../src/dsfs/forecast/oracle.py).
- Tighten [ForecastFeatureRecord](../src/dsfs/models/forecast_feature.py) from `extra="allow"` to `extra="forbid"`.
- Reuse `DEFAULT_STALENESS_THRESHOLD_DAYS` in [oracle.py:160](../src/dsfs/forecast/oracle.py).
- `functools.cache` on `get_settings()` in [config.py](../src/dsfs/config.py).

Explicitly out of scope: ledger O(N) append optimization (defer to production gap), fresh install verification (env-level).

---

## Layer 2 — Extraction validity additions (Gate C, D)

Provisional D2 alone does not answer Gate C. Two additions:

### L2a — Independent-review sample

Pick 50 notes at random from D1; one team member (not the extractor author) labels them blind against the D2 contract. Compute inter-annotator agreement and macro-F1 of the extractor against those labels. Report separately from the provisional D2 dev metric. ~1 day of human time.

If no second reviewer is available, M12 must state this and downgrade Gate C to "not evaluated independently."

### L2b — Entity-paraphrase stress test

Extend [synth/generator.py](../src/dsfs/synth/generator.py) with a `--paraphrase-entities` mode that emits notes using nicknames, hierarchy references, and pronouns for the entity mention. Re-run extractor; report entity-resolution recall. The current exact-string [entity_resolution.py](../src/dsfs/extraction/entity_resolution.py) will fail cleanly, which is the Gate D measurement we need.

### L2c — Adversarial vocabulary generalization

Reuse the D4 vocab-drift scenario (built in M10) to measure extraction accuracy on drifted-vocab notes. Report drift-window accuracy separately from in-distribution accuracy. This is the closest available check that rules-only does not merely memorize templates.

---

## M9 — Controlled evaluation and ablation matrix (Gates F, G)

### Scope

New modules under `src/dsfs/evaluation/`:

- **`ablation.py`** — parameterize feature construction so a single call produces variants for each row of the ablation matrix from [08-forecasting-experiment-design.md](08-forecasting-experiment-design.md): signal-presence-only, direction-only, +magnitude, +effective-time, +certainty, aggregate-only, note-count-only, no-decay. Reuse `run_experiment` per variant.
- **`statistics.py`** — `bootstrap_ci(errors, n=1000, seed=...)`, `paired_diff_test(a_errors, b_errors)` via pure-numpy paired permutation (no scipy).
- **`report.py`** (extended) — table per ablation × segment × horizon with MASE, MAE, bias, incremental lift, and CI. Mandatory caveat verbatim.

### Segmentation dimensions

- Per horizon.
- Per generator segment (product family, customer tier — only what the generator actually produces; never fabricated).
- **Signal-exposed subset** (Gate F): origins where any signal was active at cutoff.
- **Entity-resolved-only subset** (Gate D): origins after dropping rows where entity resolution abstained.
- **Early-signal subset** (Gate B under synthetic ideal): origins where the extracted signal predates the demand change per ground truth. Lift on early vs. late is the closest POC-scope measurement of the value of earliness.

### Decision logic

Docs/08 five-branch tree, driven by CIs not point estimates. "B > A" means CI for lift excludes 0.

### Tests

Bootstrap CI shape/reproducibility; paired-diff on known-effect synthetic data; segment aggregation matches manual computation; signal-exposed subset filter correct.

---

## M10 — Lineage, freshness, drift (Gate I)

### Scope

New modules under `src/dsfs/`:

- **`lineage.py`** — `trace_feature(feature_row) -> LineageChain` returning `feature → signals → source_evidence → source_note_id`. CLI: `dsfs-lineage`.
- **`freshness.py`** — per feature row: `feature_generated_at - max(signal.available_at)` and `cutoff - max(signal.available_at)`. Aggregate per-entity, per-window.
- **`drift/`** package:
  - `detectors.py` — pure-numpy `ks_two_sample`, `chi_square_categorical`.
  - `calibration.py` — run detectors on synthetic no-drift windows first; record empirical false-alert rate.
  - `monitors.py` — layered signal table from [10-drift-monitoring-plan.md](10-drift-monitoring-plan.md): raw-text, extraction, feature, feature↔demand, forecast.
  - `alerting.py` — test AND effect-size threshold AND persistence across 2 windows (per docs/10 alerting discipline).
  - `report.py` — writes `reports/drift_<run>.md` with detection rate, calibrated false-alert rate, per-scenario lead time = `degradation_confirmed_at - monitor_first_fired_at`. Lead time and false-alert rate always reported together.

### D4 dataset

Extend generator with `--drift-scenario` param injecting one of the seven seeded scenarios at a known week. Persist injection metadata separately (never mixed into D1).

### Tests

Lineage round-trip (feature → signal → note text); false-alert calibration on no-drift synthetic; drift detection on each seeded scenario; PIT-violation-count monitor hard-fail immediate.

---

## M11 — End-to-end orchestrator

`src/dsfs/orchestrate.py` (Python module, cross-platform):

```
dsfs-run --config configs/e2e.yaml --output reports/run_<ts>/
```

Steps chain existing `main`s:
1. `synth.pipeline` → D0, D1, D4
2. `extraction.pipeline` → ledger, D2 (provisional)
3. `evaluation.pipeline` → extraction report
4. `features.pipeline` → D3
5. `forecast.pipeline --ablation full` → forecast + ablation reports
6. `drift.report` → drift report
7. `lineage` sample → traces for N random features
8. `manifest.json` listing every artifact SHA-256 and every code SHA-256

### Tests

One true end-to-end smoke test (`tests/test_e2e_smoke.py`): small config, must complete without intervention and produce every artifact listed in [00-development-requirements-spec.md](00-development-requirements-spec.md) Q6.

---

## M12 — Findings report, organized by Gates

Deliverable is docs, not code.

### `docs/17-poc-findings.md`

```
1. Which gates the POC addressed (C, D, E, F, G, I under synthetic conditions)
2. Which gates the POC did NOT address (A, B, H) — why, and what real data
   would be needed
3. Results per success layer:
   - Signal validity — planted by construction; not measured
   - Extraction validity — self-scored D2 + independent 50-note sample +
     entity-paraphrase result + adversarial-vocab result
   - Forecast value — decision-logic branch fired, CIs, per-horizon,
     per-segment, signal-exposed, early-signal subsets
   - Operational value — lineage coverage, freshness distribution, drift
     detection rate + calibrated false-alert rate + lead time per scenario
4. Decision-logic branch fired + CIs
5. Mandatory caveat from 09-evaluation-plan.md, verbatim
```

### `docs/18-production-gap.md`

Extends [01-poc-scope-and-non-goals.md](01-poc-scope-and-non-goals.md) with observed results. Every non-goal either still excluded or newly justified in-scope. Priority-ordered production gaps:

1. Real-corpus prevalence and lead-time study (Gate A, B).
2. Entity master-data resolution at production scale (Gate D).
3. Human-gold annotation program (Gate C at production quality).
4. Business-decision impact study — asymmetric costs of over/under-forecasting (Gate H).
5. Extraction beyond rules — NER/local-LLM feasibility check per [05-technology-decision-matrix.md](05-technology-decision-matrix.md).
6. Real-time or batch serving decision — the localhost callable is a POC surface, not a production API.

---

## Sequencing

```
Week 1
  Day 1     Track A correctness fixes (A1) + tests → PR #1
  Day 2     Multi-horizon ridge (A2) + Track A cleanups (A3) → PR #2
  Day 3     Independent-review sample setup (L2a) + entity-paraphrase mode
            in synth (L2b) → PR #3
  Day 4-5   M9 ablation runner + statistics with new segments → PR #4

Week 2
  Day 1     M9 report + decision logic → PR #4 finalize
  Day 2-3   M10 lineage + freshness + D4 scenarios (incl. vocab drift
            reused for L2c) → PR #5
  Day 4-5   M10 drift detectors + calibration + report → PR #6

Week 3
  Day 1     M11 orchestrator + e2e smoke → PR #7
  Day 2     Full M11 run + human-review sample scored (L2a)
  Day 3-4   M12 findings organized by Gates + production-gap doc → PR #8
```

## Risks

- **M10 drift calibration is the widest unknown.** False-alert rate depends on window size × detector × generator variance. Budget an extra day; if unstable, widen effect-size thresholds and note it.
- **Ablation runtime.** 9 ablations × 4 arms × N origins × H horizons. Cache the (entity × cutoff) grid across arms; precompute features once per ablation.
- **Human reviewer availability.** L2a assumes one team member can label 50 notes. Without it, Gate C stays self-scored — must be flagged in M12.

## Open questions

1. Is a second reviewer available for L2a? *If no, ship M12 saying so.*
2. Entity paraphrase scope — nicknames only, or nicknames + pronouns + hierarchy? *Recommend all three.*
3. Merge cadence — per-milestone PRs (as above), or milestone-batched? *Recommend per-milestone.*
