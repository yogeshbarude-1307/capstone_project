# 10 — Drift / Monitoring Plan

## Layered hierarchy (`CONFIRMED` — repeated in every source document)

```
Raw text / writing behavior
        ↓
Extraction behavior
        ↓
Extracted feature distribution
        ↓
Feature ↔ future-demand relationship (concept drift)
        ↓
Forecast performance
```

A drift alert is **evidence of change**, not proof that the forecast has been harmed. The two must be reported separately, and a change at one layer should be traceable toward (or ruled out from) the layers below it.

## What is monitored at each layer (`PROPOSED`)

| Layer | Signals |
|---|---|
| Raw text | Note count/window, note length distribution, source-type mix, vocabulary/paraphrase distribution (optionally via a local sentence-embedding distance, not a hosted embeddings API), duplicate rate |
| Extraction | `signal_type` mix, abstention/`NO_SIGNAL` rate, `validation_status` failure rate, `business_certainty` distribution, evidence-coverage rate, extraction latency |
| Features | Missingness, staleness rate, feature-value distributions (numeric via KS, categorical via chi-square), point-in-time-violation count (must always be zero, not just "low") |
| Feature↔demand relationship | Rolling-window correlation/association between key features and subsequently realized demand; a change here (concept drift) can occur even when the feature distribution itself (covariate) is stable — the two are tracked as distinct phenomena |
| Forecast performance | Rolling MASE/bias on mature (fully realized) origins only |

## Detection method (`PROPOSED`)

- Numeric fields: Kolmogorov–Smirnov two-sample test against a calibrated reference window.
- Categorical fields: chi-square / Fisher-style test against reference proportions.
- Text-semantic drift (optional stretch): distance between local sentence-embedding distributions (reference vs. monitored window) — no hosted embedding API; use a locally-run embedding model or skip this refinement if local compute doesn't support it, falling back to the cheaper lexical/vocabulary statistics.
- Calibrate every detector on **synthetic no-drift windows first**, to characterize its null/false-alarm behavior before it is ever used against a seeded-drift window.

## Alerting discipline (`PROPOSED`)

- Require the statistical test **and** a minimum effect-size/distance threshold — p-values alone are not sufficient given how sample size affects significance.
- Require persistence across **at least two consecutive monitoring windows** before flagging, except for hard schema/PIT violations, which are always immediate and always critical.
- Escalate to "investigate forecast impact" only when a feature/extraction-layer flag coincides with (or precedes) a later confirmed forecast-performance change — this is exactly the lead-time measurement the seeded D4 scenarios are designed to produce.

## Seeded synthetic drift scenarios (`CONFIRMED` list, see D4 in `06-synthetic-data-design.md`)

Vocabulary/paraphrase shift; new abbreviations; changed source-type mix; changed note length distribution; changed proportion of direction classes; increased contradiction rate; and — the most important one — a deliberate change in the **relationship** between an extracted feature and subsequently realized demand (concept drift), which a covariate-only monitor would miss entirely.

## Drift lead time (`PROPOSED` metric)

`drift_lead_time = (time forecast degradation is confirmed) - (time the relevant monitor first fired, persistently)`. Because the injection time in D4 is known exactly, this is measurable precisely in the POC — report it per scenario, and report the calibrated false-alert rate on the matched no-drift control window alongside it, never lead time alone.

## Explicit caveat (`CONFIRMED`)

Synthetic drift experiments demonstrate that the *monitoring mechanics* work and can measure lead time under a known, controlled injection. They do not establish real production drift behavior, which depends on how real writing/business behavior actually changes over time — a fact this POC cannot observe.
