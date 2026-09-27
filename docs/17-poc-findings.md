# 17 — POC Findings

Written 2026-09-27, from a real `dsfs-run` execution at POC default scale
(40 entities, 104 weeks, seed 42 — `configs/e2e_full.json`), plus dedicated
tests exercising the entity-paraphrase and drift-scenario stress tests at the
same scale. No numbers in this document are invented; every figure below cites
its source report or test.

## 1. Which gates this POC addressed

Per the Phase One research report's gate chain (A→I), this POC — entirely
synthetic, entirely offline — can only address a subset:

| Gate | Addressed? | How |
|---|---|---|
| A — signal exists in real notes | **Not addressed** | Planted by generator construction; cannot be tested without real data |
| B — available early enough | **Not addressed** (synthetic-ideal only) | Generator controls lead time by design; no real-timestamp reliability evidence |
| C — extractable accurately | **Partially addressed** | Provisional self-scored D2 only (see §3); independent human review not completed this session |
| D — entity/time resolution | **Addressed, and found deficient** | Entity-paraphrase stress test — see §3 |
| E — duplicates/conflicts controlled | **Addressed** | Reconciliation/reversal logic, tested (`tests/extraction/test_reconciliation*.py`) |
| F — incremental predictive value | **Addressed** | 4-arm experiment + ablation matrix — see §4 |
| G — model can exploit it | **Addressed** | Same 4-arm experiment |
| H — business-decision impact | **Not addressed** | Requires real asymmetric-cost data this POC does not have |
| I — operable (lineage/freshness/drift) | **Addressed at POC scope** | See §5 |

## 2. Signal validity (Gates A, B) — not measured

The synthetic generator plants a causally-consistent signal by construction
(`docs/06-synthetic-data-design.md`): notes are rendered from `Knowable` only,
demand is realized from `HiddenState` independently, and `tests/synth/test_leakage.py`
enforces this separation at the type level. This means the POC can demonstrate
that *if* a signal with the assumed properties exists, the pipeline can find
and exploit it — it cannot demonstrate that real account/service/supplier notes
actually contain such a signal, at what prevalence, or with what real lead time.
**This is the single most important limitation of every result below.**

## 3. Extraction validity (Gate C, D)

### Self-scored provisional result (Gate C)

From `dsfs-evaluate` against the 40-note provisional D2 starter
(`data/annotations/d2_starter.json`), `challenge / provisional` cohort:

| Metric | Value |
|---|---:|
| Actionable-event macro-F1 | 0.4158 |
| Signal-type accuracy | 0.8500 |
| Direction accuracy | 0.6500 |
| Schema valid-record rate | 1.0000 |
| Abstention precision / recall | 0.6154 / 1.0000 |
| Unsupported-inference rate | 0.0616 |

**This is a development diagnostic, not an independent measurement** — the
labels were authored by the same process that wrote the extraction rules being
scored. `scripts/select_review_sample.py` and
`docs/annotations/human_review_instructions.md` build the infrastructure for
an independent 50-note review (reusing the same evaluation machinery so the
scores are directly comparable), but **the labeling itself was not completed
in this session** — no second reviewer was available. Gate C therefore remains
self-scored only. This is the top-priority item in `18-production-gap.md`.

### Entity resolution stress test (Gate D)

Real numbers at POC scale (40 entities, 104 weeks, seed 5), comparing the
current exact-string `entity_resolution.resolve_entities` against two note
corpora that differ only in how the entity is mentioned:

| Entity mention mode | Notes with a mention | Resolved | Recall |
|---|---:|---:|---:|
| `none` (canonical entity_key rendered verbatim — current POC default) | 679 | 679 | **100.0%** |
| `aggressive` (nicknames, pronouns, hierarchy references) | 679 | 0 | **0.0%** |

This is not a synthetic-generator artifact to explain away: it is the honest
consequence of the current resolver being exact-string match against a known-
entity set, with mentions in the default corpus happening to equal the
canonical key. The moment a note refers to an entity the way a real person
would — "they," "the account we discussed," a nickname — recall drops to zero.
**Entity resolution is very likely a bigger production risk than extraction
accuracy itself**, exactly as the Phase One research report anticipated.
Reproducible via `tests/extraction/test_entity_resolution_paraphrase.py` or
`dsfs-generate --paraphrase-entities aggressive`.

## 4. Forecast value (Gates F, G)

### Primary 4-arm result

From `reports/forecast/experiment_results.md`, full POC scale (40 entities,
104 weeks, `train_weeks=52`, `horizon_weeks=4`, `ridge_alpha=1.0`,
`lag_weeks=[1,2,4,8,13,26]`, 7,800 origins per arm):

| Arm | Description | MASE | MAE | Bias | Lift vs A |
|---|---|---:|---:|---:|---:|
| A | Tabular only (baseline) | 1.4727 | 28.01 | −1.03 | +0.00% |
| B | Oracle (ground truth) | 1.5187 | 28.88 | −0.27 | **−3.13%** |
| C | Extracted signals | 1.6251 | 30.91 | −2.23 | −10.35% |
| D | Shuffled control | 1.5716 | 29.89 | −0.53 | −6.72% |

**Decision-logic branch fired: B ≈ A.** Per docs/08: *"the planted signal
itself carries no forecastable information at the current feature
representation — rethink the hypothesis or the feature design before
touching the extractor."* Even the oracle arm (upper bound, using the
generator's own ground truth, bypassing extraction entirely) does not beat
the tabular baseline with this feature representation and model configuration.

This is a genuine, not-favorable-looking result, and it is reported as such —
suppressing or reframing it would violate the mandatory caveat this project
was built around. Two honest candidate explanations, neither yet tested:

1. **Feature representation.** The oracle features
   (`forecast/oracle.py`) are raw counts/quantities merged alongside lag/
   seasonal tabular features without relative scaling; a ridge model with
   `alpha=1.0` may be under- or over-regularizing this mixed-scale input.
2. **Model capacity/tuning.** No hyperparameter search was run; `ridge_alpha`
   and the lag structure were fixed defaults, not tuned for this signal.

Both are next steps, not resolved by this POC — see `18-production-gap.md`.

**Arm D (shuffled control) also underperforms baseline** (−6.72%), not
outperforms it — so the leakage-check branch (`D shows meaningful *positive*
lift`) did not fire. This is consistent with, not contradictory to, the B≈A
finding: no arm using signal features beats the baseline here.

### Ablation matrix

**Note on scale:** the bootstrap-lift computation had a real bug (found while
preparing this document — see `13-risks-and-dependencies.md`) where arm A's
*signed* per-origin errors were compared against every ablation arm's
*absolute* errors, producing nonsensical percentages (e.g. "−2905.86%" with a
[−25282%, +10271%] CI) in the original full-scale (40-entity) run. The primary
4-arm result in §4 above is unaffected — it uses a separately, correctly
implemented path (`ExperimentMetrics`) already covered by existing tests. After
fixing the bug, the ablation matrix below is from a re-run at reduced entity
count (10 entities, same 104-week/52-train/4-horizon temporal config as the
full run — `configs/e2e_ablation_recheck.json`) rather than the original
40-entity run, purely because the per-origin multi-horizon retraining in
`run_arm` makes the full ablation matrix computationally heavy at full scale
(the original 40-entity run took 129 minutes; this 10-entity recheck took 24).
This is a real, documented scaling characteristic, not a shortcut around the bug.

| Ablation | Arm B MAE | Arm B lift (95% CI) | Arm C MAE | Arm C lift (95% CI) |
|---|---:|---:|---:|---:|
| note_count_only | 26.37 | −2.09% [−4.23%, −0.18%] | 26.43 | −2.32% [−4.62%, −0.22%] |
| presence_only | 26.59 | −2.93% [−5.19%, −0.84%] | 26.53 | −2.70% [−5.15%, −0.43%] |
| direction | 26.08 | −0.95% [−3.29%, +1.35%] | 25.98 | −0.59% [−2.91%, +1.76%] |
| magnitude | 26.08 | −0.95% [−3.29%, +1.35%] | 25.98 | −0.59% [−2.91%, +1.76%] |
| effective_time | 27.10 | −4.92% [−7.90%, −1.97%] | 28.46 | −10.18% [−14.74%, −5.39%] |
| full | 27.10 | −4.92% [−7.90%, −1.97%] | 28.46 | −10.18% [−14.74%, −5.39%] |

(Baseline arm A MAE at this scale: 25.83.)

The clearest pattern: **`direction`/`magnitude` are the least harmful
representations** (lift CIs straddle zero — not distinguishable from no
effect), while **`effective_time` is where both arms' loss concentrates**
(−4.92% for oracle, −10.18% for extracted, both CIs excluding zero). Since
`effective_time` and `full` are identical (no richer representation is
implemented beyond it), this points at the `nearest_effective_start_days`/
`delay_count_90d`/`days_since_latest_signal` feature group specifically as
the most likely place the current representation actively hurts the model,
not just fails to help. That's a concrete, actionable next step (see
`18-production-gap.md` item 5) — narrower than "the whole feature
representation might be wrong."

Per-horizon breakdown (arm C, full ablation, same 10-entity recheck run):

| Horizon (weeks) | MAE | Origins |
|---:|---:|---:|
| 1 | 22.37 | 490 |
| 2 | 26.88 | 490 |
| 3 | 29.76 | 490 |
| 4 | 34.98 | 480 |

Signal-exposed subset: 377 / 1,950 origins (19.3%) had an active extracted
signal at cutoff.

Not implemented in this POC's ablation matrix (documented, not fabricated —
see `evaluation/ablation.py:NOT_IMPLEMENTED`): business_certainty/conditionality
features, aggregate-only cross-entity features, rules-vs-NER-vs-LLM
representation comparison, decayed/windowed signal weighting.

## 5. Operational value (Gate I)

- **Lineage:** 20/20 sampled D3 feature rows (`dsfs-lineage`, seed 42) traced
  completely back to their contributing signal(s) and exact source-text span.
  100% resolution at this scale — no broken lineage chains found.
- **Freshness:** feature-layer staleness reuses `days_since_latest_signal`/
  `staleness_status` already in D3; extraction-layer processing latency
  (`extracted_at - available_at`) is measured per signal, always ≥ 0 by
  construction and verified so in `tests/lineage/test_freshness.py`.
- **Drift:** 5 of 7 docs/10 seeded scenarios are implemented and independently
  verified (`tests/drift/`) with real detection + latency + calibrated
  false-alert rate, always reported together per docs/10's discipline.
  `direction_class_shift` and `concept_drift` are not implemented — both would
  require touching `latent.py`/`demand.py`, the causal-separation-critical
  modules `test_leakage.py` protects. The `e2e_full.json` config used for the
  headline forecast result above did not seed a drift scenario
  (`drift_scenario="none"`), so the orchestrator's own drift step reports
  "skipped" for that run — drift detection is demonstrated separately via the
  dedicated test suite, not as part of the headline 4-arm run.
- **PIT invariant:** re-checked directly against the ledger (not inferred from
  a field that's always "now") — zero violations found in the full-scale run's
  D3 (`dsfs.drift.monitors.count_pit_violations`).

## 6. Decision-logic branch and mandatory caveat

**Branch fired: B ≈ A.** Per docs/08, this POC's own decision framework calls
for rethinking the hypothesis or the feature/model design before iterating on
the extractor — the bottleneck (if there is one worth chasing) is upstream of
extraction quality, at the level of "does this feature representation and
model configuration expose the planted signal at all."

> This POC demonstrates that a deliberately planted, causally-consistent early
> signal can be recovered from synthetic notes and shown to add measurable
> value to a forecast under controlled conditions. It does **not** demonstrate
> that real company account/service/supplier notes contain comparable
> predictive information, at what prevalence, or with what real lead time.
> Real-data validation is a required, separate, subsequent gate before any
> production claim is made.

In this run, even the "shown to add measurable value under controlled
conditions" half of that sentence did not hold at default configuration — a
further reason for caution before any interpretation of Gate F/G as "passed."
