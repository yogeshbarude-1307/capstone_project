# 08 — Forecasting Experiment Design

## The controlling experiment (`CONFIRMED` — the single most repeated design element across all five source documents)

Four arms, everything held identical except the qualitative-signal input:

| Arm | Tabular history | Qualitative input | Purpose |
|---|---|---|---|
| **A — Baseline** | Yes | None | Current-equivalent benchmark |
| **B — Oracle signal** | Yes | Features built from the synthetic generator's own ground truth (step 1–2 of `06-synthetic-data-design.md`, not the rendered note) | Upper bound: "is there even a signal worth extracting?" |
| **C — Extracted signal** | Yes | Features built from the real end-to-end extraction pipeline's output | End-to-end value: what the actual system achieves |
| **D — Shuffled/time-shifted signal** | Yes | The same extracted signals, but reassigned to the wrong entity/time | Negative control against leakage or spurious correlation |

Same forecast dates, same training window, same tabular inputs, same forecasting algorithm, same hyperparameter policy across all four arms. Only the qualitative-feature input differs.

## Decision logic (`CONFIRMED`)

- **B ≈ A** → stop; the planted signal itself carries no forecastable information at the current feature representation — rethink the hypothesis or the feature design before touching the extractor.
- **B > A but C ≈ A** → the oracle signal is useful but the extraction/representation pipeline is the bottleneck; iterate on `07-extraction-pipeline-design.md`.
- **C approaches B** → the extractor retains most of the usable planted signal; end-to-end mechanics work.
- **D also improves** → investigate leakage, a PIT bug, or confounding before believing any of the above.
- **C improves in aggregate but harms specific segments** → aggregate lift is not sufficient evidence; report segment-level results.

## Evaluation protocol (`CONFIRMED`)

**Rolling-origin time-series cross-validation only** — never a random train/test split. Every training window contains only observations available before its forecast origin; every qualitative feature used in that window additionally satisfies the point-in-time eligibility rule from `03-data-model.md` (`available_at <= cutoff`). For each origin: freeze tabular inputs as of cutoff, freeze eligible signals as of cutoff, generate the forecast, then compare against demand realized strictly after cutoff.

## Metrics (`CONFIRMED` primary choice, `PROPOSED` secondary set)

- **Primary:** MASE (scale-independent, appropriate for comparing across heterogeneous synthetic series).
- **Secondary:** MAE, signed bias (over/under-forecasting), and incremental error reduction = `(baseline_error - enhanced_error) / baseline_error`.
- Report overall, on the **signal-exposed subset only** (forecast origins/entities where a signal was actually active), by forecast horizon, and by any synthetic segment the generator defines (e.g. product family, customer tier) — never fabricate a segmentation that the generator doesn't actually produce.

## Ablation matrix (`CONFIRMED` list, `PROPOSED` exact set for the POC)

| Ablation | Tests |
|---|---|
| Signal presence only (no direction/magnitude/time) | Whether "a note exists" alone carries value, or richer structure is required |
| Direction only | Minimum useful representation |
| + magnitude | Value of explicit quantity extraction |
| + effective time | Value of temporal normalization |
| + business_certainty / conditionality | Value of modality/hedging information |
| No entity-specific resolution (aggregate-only features) | Value of entity mapping |
| Rules-only extraction vs. hybrid vs. LLM-degraded-off | Whether the semantic LLM stage is actually earning its cost (ties directly to the degradation path in `07-extraction-pipeline-design.md`) |
| No recency/decay weighting vs. decayed/windowed | Whether temporal weighting of signals matters |
| Note-count-only feature (ignores all structure) | Negative control: is structure actually needed, or would raw note volume alone look predictive? |

## Provisional success gates (`PROPOSED`, carried from the source research, pending business ratification)

- Oracle-enriched model (arm B) shows a credible, statistically distinguishable positive lift over baseline (arm A) on the primary metric — if not, the POC concludes negative on the core hypothesis regardless of extraction quality.
- Extracted-feature model (arm C) preserves a material fraction of the oracle lift; exact minimum fraction is **OPEN** (business-approved minimum forecast lift is not yet defined — see `14-open-questions.md`).
- Shuffled control (arm D) shows no meaningful lift — any lift here is treated as a leakage bug, not a result.
- Zero known point-in-time leakage violations in the automated leakage test suite (`11-testing-strategy.md`) — this gate is non-negotiable, unlike the numeric lift thresholds.
