# 09 — Evaluation Plan

## Two independent experiments, never merged (`CONFIRMED`)

**Extraction experiment** answers: *did the system recover what the note actually said?*
**Forecast experiment** answers: *did the resulting feature improve the forecast?*

A high-accuracy extractor whose output carries no forecast-usable information, and a noisy extractor that still helps the forecast because a strong directional signal survives the noise, are both possible and both informative — collapsing the two experiments into one score would hide either finding.

## Extraction metrics (`CONFIRMED` list, independent of forecast results)

| Layer | Metrics |
|---|---|
| Event detection | Precision, recall, macro-F1 by `signal_type` |
| Schema | Valid-record rate; semantic cross-field validation failure rate |
| Grounding | Evidence-span coverage; unsupported-inference rate (populated field with no `evidence_ref` support) |
| Direction / type | Accuracy, macro-F1 |
| Negation | Precision/recall/F1 on the dedicated negation subset of D2/D5 |
| Conditionality | Precision/recall/F1 on the dedicated conditional subset |
| Temporal | Normalized-period exact-match / interval-overlap accuracy against `authored_at`-relative ground truth |
| Magnitude | Exact/tolerance-band match; unit accuracy |
| Entity resolution | Accuracy on resolvable cases; correct-abstention rate on ambiguous/unresolvable cases |
| Abstention | Precision/recall of the `NO_SIGNAL`/`REVIEW` decision itself, scored against D2's abstention-reason labels |

Report all of the above using the **error taxonomy from `07-extraction-pipeline-design.md`** so failures are diagnosable, not just scored.

## Forecast metrics (`CONFIRMED`, see `08-forecasting-experiment-design.md` for the full protocol)

MASE primary; MAE, signed bias, and incremental-lift percentage secondary; reported overall, on the signal-exposed subset, by horizon, and by ablation arm.

## Statistical interpretation (`PROPOSED`)

- Report the distribution of paired per-origin/per-series loss differences (baseline vs. enhanced), not just the two aggregate numbers — a mean improvement can hide high variance or a few outlier series driving the result.
- Where sample size allows, bootstrap a confidence interval on the incremental-lift percentage.
- Treat statistical significance as necessary but not sufficient — a technically significant lift with no plausible operational meaning is not treated as a POC success on its own.

## Reproducibility requirement (`CONFIRMED`)

Every reported result must be regenerable from: the pinned `schema_version`, `extractor_version`, `extraction_config_version`, `feature_definition_version`, the forecast model config, and the exact D2/D3 dataset snapshot used. This is tested directly (see `11-testing-strategy.md`, reproducibility test).

## The mandatory reporting caveat (`CONFIRMED`, must appear verbatim in the final POC report)

> This POC demonstrates that a deliberately planted, causally-consistent early signal can be recovered from synthetic notes and shown to add measurable value to a forecast under controlled conditions. It does **not** demonstrate that real company account/service/supplier notes contain comparable predictive information, at what prevalence, or with what real lead time. Real-data validation is a required, separate, subsequent gate before any production claim is made.
