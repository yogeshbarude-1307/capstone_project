# 19 — Remaining Implementation (as of 2026-09-27)

Snapshot of what's done and what's left against the plan in
[16-revised-execution-plan.md](16-revised-execution-plan.md). Written so work can
resume cold in a future session without re-deriving status from git history.

## Done (PRs #1–8) — all code and documentation complete

| PR | Scope | Status |
|---|---|---|
| #1 | Track A correctness fixes (6 bugs) | Done, tested |
| #2 | Multi-horizon ridge + cleanups | Done, tested |
| #3 | Layer 2 extraction-validity infra (entity paraphrase, human-review scaffold) | Done, tested |
| #4 | M9 ablation matrix + statistics | Done, tested |
| #5 | M10a lineage + freshness + D4 drift-scenario generator | Done, tested |
| #6 | M10b drift detectors + calibration + alerting + report | Done, tested |
| #7 | M11 end-to-end orchestrator + smoke test | Done, tested |
| #8 | M12 findings + production-gap docs, populated from real runs | Done |

**297 tests passing** (baseline was 181 at session start).

### Bugs found and fixed along the way (beyond the original review list)

These were **not** in the original flaw list — found while building on top of the
existing code and confirmed empirically against real generated data, not fixtures:

1. **`forecast_cutoff` dtype mismatch** ([harness.py](../src/dsfs/forecast/harness.py)) —
   `signal_features.forecast_cutoff` is an ISO string; D0's `period_start` is a
   `datetime.date`. They never compared equal, so **arms B/C/D silently received zero
   merged signal features in every real run** — numerically identical to arm A. Fixed
   with `normalize_cutoff_column()`. Any forecast report generated before this fix was
   invalid; re-run confirmed in `docs/17-poc-findings.md`.
2. **`build_d3` referenced a nonexistent `week_start` column** ([features/pipeline.py](../src/dsfs/features/pipeline.py))
   — real D0 only has `period_start`. `dsfs-features` had never worked on real
   generated data.
3. **Non-ASCII `≈` crashed on Windows cp1252 console** in the decision-logic report —
   reverted to ASCII `~`.
4. **`evaluate_arm` silently returned NaN metrics** when `train_weeks`/`lag_weeks`
   were too large relative to `n_weeks` (zero origins produced) — now raises a clear
   `ValueError` naming the likely cause instead of propagating NaN downstream.
5. **Ablation report's bootstrap lift mixed signed and absolute error arrays**
   ([forecast/pipeline.py](../src/dsfs/forecast/pipeline.py)) — arm A's baseline errors
   were signed (`actuals - predictions`) while every ablation row's errors were
   absolute (`np.abs(...)`), producing nonsensical lift percentages in the thousands
   (found while writing `docs/17-poc-findings.md` from a real full-scale run). Fixed;
   also removed a redundant full ablation-matrix recomputation the report was doing
   just to extract one row it had already computed.

## M11 orchestrator details (PR #7)

- [src/dsfs/orchestrate.py](../src/dsfs/orchestrate.py) — chains synth → extraction →
  evaluation → features → forecast(+ablation) → drift → lineage into one run,
  producing `manifest.json` (per-artifact SHA-256, code SHA-256) and a persisted
  `reports/lineage/lineage_sample.md` (closes output (f) from
  `docs/00-development-requirements-spec.md` §6 as a file artifact like the others).
- [configs/e2e_smoke.json](../configs/e2e_smoke.json), [configs/e2e_full.json](../configs/e2e_full.json).
- New console script `dsfs-run`.
- The initial smoke config was too heavy (`n_weeks=80` × `--ablation full` × 3 tests
  took 280s+); trimmed to `n_entities=3, n_weeks=45, horizon_weeks=1, min_origins=1`
  — full smoke run now ~11s.
- **Known scaling characteristic, not a bug:** the direct multi-horizon fix (PR #2)
  retrains a fresh ridge model per origin per horizon. At full POC scale (40 entities,
  104 weeks, `train_weeks=52`, `horizon_weeks=4`, `--ablation full`), a complete
  `dsfs-run` took **129 minutes**; a 10-entity version of the same temporal config took
  24 minutes. Fine for a POC's occasional full run; would need batching/vectorizing the
  per-origin retraining loop before any more frequent (e.g. CI) use at full scale.

## M12 findings (PR #8) — real numbers, not invented

- [docs/17-poc-findings.md](17-poc-findings.md) — populated from an actual full-scale
  `dsfs-run` (40 entities, 104 weeks) plus a corrected 10-entity ablation re-run (see
  bug #5 above) and dedicated entity-paraphrase/drift tests at POC scale.
  **Headline result: decision-logic branch B ≈ A** — even the oracle arm (bypassing
  extraction entirely) did not beat the tabular baseline at default configuration.
  Reported honestly, not reframed.
- [docs/18-production-gap.md](18-production-gap.md) — priority-ordered gaps, including
  a POC-scale entity-resolution measurement (100% recall → 0% recall the moment notes
  use pronouns/nicknames instead of literal entity keys) and a concrete, narrowed next
  step from the ablation matrix (the `effective_time` feature group, not the whole
  representation, is where both arms' loss concentrates).
- [docs/12](12-implementation-milestones.md), [docs/13](13-risks-and-dependencies.md),
  [docs/14](14-open-questions.md), [README.md](../README.md) updated to reflect M9-M12
  complete and the realized risks found along the way.

## Outside code entirely (manual task, not blocked on implementation)

- **L2a independent human review** ([docs/annotations/human_review_instructions.md](annotations/human_review_instructions.md)) —
  the scaffold (`scripts/select_review_sample.py`) is built and tested, but the actual
  labeling by a second person (not the extractor's author) was **not completed this
  session** — no second reviewer was available. `docs/17-poc-findings.md` and
  `docs/18-production-gap.md` both state this plainly: Gate C (extraction validity)
  remains self-scored only (macro-F1 0.4158 on the 40-note provisional D2 starter).
  This is the top open item if the project continues.

## Everything else

No other implementation work is queued. Remaining next steps are the ones
`docs/18-production-gap.md` lists as gaps requiring either real data access (gaps 1-4)
or a person's time (the human review above, or the feature-scaling/ridge-alpha
experiments in gap 5) — none of them are more code to write in this repo's current
synthetic-POC scope.
