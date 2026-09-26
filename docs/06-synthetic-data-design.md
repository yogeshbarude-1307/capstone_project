# 06 — Synthetic Data Design

## The one rule that governs everything here (`CONFIRMED`)

**The generator must never let a note "know" something a real author could not plausibly have known at note time.** Three of the five source research documents flag this as the single easiest way to invalidate the whole POC: if the generator writes a note using knowledge of the future realized demand and merely timestamps it in the past, the resulting "early signal" experiment is leaked by construction — the timestamps look correct but the information flow is backwards.

### Causal generation order (`CONFIRMED`)

```
1. Generate a latent business-state trajectory per synthetic entity/product
   (a hidden, evolving "true intent" the synthetic customer/account holds).
2. At each simulated note-writing moment, derive ONLY the subset of that
   state a plausible human author could know/observe at that moment
   (partial, sometimes wrong, sometimes hedged, sometimes contradictory
   with an earlier note).
3. Render note text from that partial knowledge only, using templates +
   randomized phrasing (including deliberately hard constructions —
   negation, conditionality, vague dates, stale references).
4. ONLY AFTER note generation is complete, sample the realized demand
   trajectory -- independently, with injected noise, and a nonzero
   probability that the anticipated event never materializes at all
   (cancelled plans, unrealized expectations).
5. Assign available_at = authored_at + a small simulated ingestion delay
   (never available_at < authored_at).
```

Step 4 happening *after* and *independently* of step 3 is what makes the later forecast-lift experiment meaningful rather than circular. The generator code must be structured so that the demand-realization function has no code path that reads note text or extracted signals — only the latent state and its own noise process.

## Datasets (`PROPOSED` sizing, `CONFIRMED` purpose split)

| ID | Purpose | Content | Ground truth |
|---|---|---|---|
| **D0** | Baseline tabular forecast benchmark | Synthetic demand/shipment history + existing structured covariates, per entity/period | Actual (generator-produced) target series |
| **D1** | Extraction pipeline development | Synthetic notes generated per the causal process above, at scale (thousands) | Generator's own event metadata (useful but *not* treated as the only gold standard — see D2) |
| **D2** | Extraction gold/challenge set | A held-out, independently-labeled subset — some machine-templated, some hand-authored/hand-edited to avoid pure template memorization | Human-adjudicated labels using the canonical signal schema; oversampled for hard cases (negation, conditional, contradiction, no-signal, ambiguous entity, vague date) |
| **D3** | Point-in-time forecast dataset | D0 + only the D1/D2-derived signals eligible under the PIT rule at each rolling forecast origin | Derived, not separately labeled |
| **D4** | Drift challenge set | Seeded shifts: vocabulary/paraphrase changes, new abbreviations, changed source mix, changed direction-class proportions, changed feature↔demand relationship (concept drift) | Known injection time + type + severity, for measuring detection lead time |
| **D5** | Adversarial/safety challenge set | Malformed text, extremely long/short notes, text containing instruction-like content (prompt-injection-style probes aimed at the local LLM stage), duplicate notes, stale references ("same as last week") | Expected extraction/abstention behavior, not a demand label |
| **D6** | Reprocessing regression set | A small frozen set of D1/D2 notes, fixed forever | Re-run across extractor versions to detect unintended output drift |

Sizing (`PROPOSED`, adjust once pipeline runtime is known): D1 ~5,000–20,000 notes; D2 ~800–1,500 notes (≥100 per major `signal_type` where feasible, ≥20% explicit `NO_SIGNAL`, ≥15% explicit challenge cases); D4/D5 a few hundred notes each; D6 ~50–100 fixed notes.

## Annotation schema for D2 (`PROPOSED`)

Mirrors the signal schema in `03-data-model.md` plus: `annotator_id`, `adjudication_state` (single/double-annotated, agreed/disagreed/resolved), `ambiguity_flag`, and an explicit **abstention reason** field so "correctly declined to extract" is itself a scoreable outcome. At least 20–30% of D2 should be double-annotated and adjudicated before treating the ontology as stable.

**Critical separation:** the human-extracted *signal* (e.g. `direction=decrease, magnitude=20, magnitude_unit=percent, conditional=true`) is annotated independently from the eventual forecast *feature* (e.g. `negative_signal_90d=1`). Annotators label what the note says, not what a downstream feature-engineering step later does with it — this preserves the three-layer separation from `03-data-model.md` all the way back into the labeling process itself.

## Sampling policy (`PROPOSED`)

Report two separate views, never merged into one headline number:

- **Natural-prevalence sample** — approximates how notes would actually occur (mostly irrelevant/no-signal, a modest fraction with a genuine early demand signal). Used for end-to-end precision and forecast-value estimates.
- **Balanced/challenge sample** — deliberately over-represents rare, costly cases (cancellations, negation, large-magnitude events, contradictions) so a high aggregate accuracy can't hide systematic failure on the cases that matter most.

Splits (train/dev/test) are grouped by underlying scenario template so paraphrases of the same synthetic scenario never leak across a split boundary.

## What synthetic data can and cannot prove (`CONFIRMED`, carried into every downstream report)

It **can** demonstrate: pipeline mechanics, schema correctness, temporal/leakage handling, extraction mechanics on known constructions, feature generation, lineage, drift-detection mechanics, and whether the experimental framework can recover a *deliberately planted* signal.

It **cannot** demonstrate that real company notes contain useful predictive information, at what prevalence, or with what real lead time. Every results report produced by this POC must carry this distinction explicitly (see `09-evaluation-plan.md` and `01-poc-scope-and-non-goals.md`).
