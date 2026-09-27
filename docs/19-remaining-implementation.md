# 19 — Remaining Implementation (as of 2026-09-27)

Snapshot of what's done and what's left against the plan in
[16-revised-execution-plan.md](16-revised-execution-plan.md). Written so work can
resume cold in a future session without re-deriving status from git history.

## Done (PRs #1–6, verified green)

| PR | Scope | Status |
|---|---|---|
| #1 | Track A correctness fixes (6 bugs) | Done, tested |
| #2 | Multi-horizon ridge + cleanups | Done, tested |
| #3 | Layer 2 extraction-validity infra (entity paraphrase, human-review scaffold) | Done, tested |
| #4 | M9 ablation matrix + statistics | Done, tested |
| #5 | M10a lineage + freshness + D4 drift-scenario generator | Done, tested |
| #6 | M10b drift detectors + calibration + alerting + report | Done, tested |

**291 tests passing** as of PR #6 close (baseline was 181 at session start).

### Bugs found and fixed along the way (beyond the original review list)

These were **not** in the original flaw list — found while building on top of the
existing code and confirmed empirically against real generated data, not fixtures:

1. **`forecast_cutoff` dtype mismatch** ([harness.py](../src/dsfs/forecast/harness.py)) —
   `signal_features.forecast_cutoff` is an ISO string; D0's `period_start` is a
   `datetime.date`. They never compared equal, so **arms B/C/D silently received zero
   merged signal features in every real run** — numerically identical to arm A. Fixed
   with `normalize_cutoff_column()`. **Any forecast report generated before this fix is
   invalid and must be re-run.**
2. **`build_d3` referenced a nonexistent `week_start` column** ([features/pipeline.py](../src/dsfs/features/pipeline.py))
   — real D0 only has `period_start`. `dsfs-features` had never worked on real
   generated data.
3. **Non-ASCII `≈` crashed on Windows cp1252 console** in the decision-logic report —
   reverted to ASCII `~`.
4. **`evaluate_arm` silently returned NaN metrics** when `train_weeks`/`lag_weeks`
   were too large relative to `n_weeks` (zero origins produced) — now raises a clear
   `ValueError` naming the likely cause instead of propagating NaN downstream.

## Done (PR #7 — M11 orchestrator)

- [src/dsfs/orchestrate.py](../src/dsfs/orchestrate.py) — chains synth → extraction →
  evaluation → features → forecast(+ablation) → drift → lineage into one run,
  producing `manifest.json` with per-artifact SHA-256 and code SHA-256.
- [configs/e2e_smoke.json](../configs/e2e_smoke.json), [configs/e2e_full.json](../configs/e2e_full.json).
- [tests/test_e2e_smoke.py](../tests/test_e2e_smoke.py) — 3 tests: full artifact
  production, manifest JSON validity, and schema-failure abort behavior.
- New console script `dsfs-run`.
- The initial smoke config was too heavy (`n_weeks=80` × `--ablation full` × 3 tests
  took 280s+); trimmed to `n_entities=3, n_weeks=45, horizon_weeks=1, min_origins=1`
  (added `min_origins` passthrough in the orchestrator) — full smoke run now ~11s.

**Full suite: 296 passed** (up from 291 at PR #6 close; +2 `evaluate_arm` regression
tests, +3 e2e smoke tests), full run in ~49s.

## Not started (PR #8 — M12 findings + production gap)

Per [16-revised-execution-plan.md](16-revised-execution-plan.md), this is pure
documentation, no new code:

### `docs/17-poc-findings.md` (new)
Must be populated from a **real `dsfs-run --config configs/e2e_full.json`** output
(the manifest + forecast/ablation/drift reports it produces), not invented numbers:
1. Which gates the POC addressed (C, D, E, F, G, I) vs. did not (A, B, H), and why.
2. Results per success layer:
   - Signal validity — planted by construction, not measured.
   - Extraction validity — self-scored D2 (`d2_starter.json`) macro-F1, **plus** the
     independent human-review result if L2a labeling happened (see below) — or an
     explicit statement that it did not.
   - Forecast value — decision-logic branch fired, CIs, per-horizon/per-ablation
     table from the M9 ablation report.
   - Operational value — lineage completeness rate, freshness distributions, drift
     detection rate + calibrated false-alert rate + latency per scenario.
3. Decision-logic branch fired, stated in one bold line.
4. Mandatory caveat from [09-evaluation-plan.md](09-evaluation-plan.md), verbatim.

### `docs/18-production-gap.md` (new)
Extends [01-poc-scope-and-non-goals.md](01-poc-scope-and-non-goals.md) with observed
results. Priority-ordered gaps (from doc 16):
1. Real-corpus prevalence/lead-time study (Gate A, B).
2. Entity master-data resolution at production scale (Gate D) — cite the
   `entity_resolution_paraphrase` test results as the POC-scale evidence.
3. Human-gold annotation program (Gate C at production quality).
4. Business-decision impact study (Gate H).
5. Extraction beyond rules — NER/local-LLM feasibility per [05-technology-decision-matrix.md](05-technology-decision-matrix.md).
6. Real-time/batch serving decision.

### Other doc updates bundled into PR #8
- [12-implementation-milestones.md](12-implementation-milestones.md) — mark M9–M12
  Complete in the status table.
- [13-risks-and-dependencies.md](13-risks-and-dependencies.md) — annotate with the
  four bugs found above as realized risks, not just hypothetical ones.
- [14-open-questions.md](14-open-questions.md) — mark what M11 resolved, what's still open.
- [README.md](../README.md) — update status section (milestone count, test count).

## Outside code entirely (manual task, not blocked on implementation)

- **L2a independent human review** ([docs/annotations/human_review_instructions.md](annotations/human_review_instructions.md)) —
  someone other than the extractor's author must label the 50-note sample from
  `scripts/select_review_sample.py`. Nothing in PR #8 should claim this happened
  unless it actually did; if it didn't, M12 must say so plainly and Gate C stays
  self-scored only.

## Sequencing to finish

```
1. Re-verify PR #7 full suite green (in progress at time of writing)
2. Commit + push PR #1-7 (this session's request)
3. Run dsfs-run --config configs/e2e_full.json for real M12 source numbers
4. (Optional, manual) L2a human review labeling
5. Write docs/17-poc-findings.md + docs/18-production-gap.md from step 3's output
6. Update docs/12, docs/13, docs/14, README.md
7. Commit + push PR #8
```
