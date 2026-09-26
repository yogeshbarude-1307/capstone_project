# 07 — Extraction Pipeline Design

## Pipeline stages (`CONFIRMED` shape, `PROPOSED` implementation)

```
Raw note (SourceEvidence)
    ↓
Preprocessing / normalization  (encoding, whitespace, sentence splitting)
    ↓
Rule-based candidate extraction (spaCy Matcher/EntityRuler)
    — quantities, units, known product/customer aliases, explicit dates
    ↓
Statistical NER (spaCy statistical model, local)
    — spans for unrecognized entities/products/customers
    ↓
Local constrained-decoding LLM stage (semantic interpretation)
    — direction, negation, conditionality, business_certainty,
      effective time normalization relative to authored_at,
      evidence-span attribution
    — output is constrained to the SignalRecord JSON Schema
      (grammar/schema-constrained decoding; never free-form JSON)
    ↓
Entity resolution
    — raw mentions → resolved_entities / forecast_key using a
      synthetic local master-data lookup table
    ↓
Deterministic validator
    — schema conformance, cross-field business rules
      (e.g. "magnitude requires a unit", "end time cannot precede
      start time", "NO_SIGNAL implies direction=NA")
    ↓
Confidence / abstention decision
    — insufficient evidence -> signal_type=NO_SIGNAL or
      validation_status=REVIEW, never a forced guess
    ↓
Versioned SignalRecord written to the append-only ledger
    (with evidence_ref, extractor_version, extraction_config_version,
     extraction_run_id, extracted_at)
```

## Degradation path if the local LLM stage is infeasible (`CONFIRMED` requirement, `PROPOSED` mechanism)

The technology matrix (`05-technology-decision-matrix.md`) flags the exact local model/runtime as `OPEN` pending a feasibility check. If no local constrained-decoding model runs acceptably on the available hardware, the pipeline **degrades gracefully**:

- Rules + NER still run and populate `entity_mentions`, explicit quantities/units, and explicit dates.
- Fields that depend on sentence-level semantics (`direction`, `negated`, `conditionality`, `business_certainty`) default to `UNKNOWN` with `validation_status=REVIEW` rather than being guessed.
- This degraded mode is still evaluated (arm C in the forecast experiment uses whatever the actual pipeline produces) — it is documented as a lower bound, and the LLM stage remains a swappable, clearly-labeled "not yet enabled" component behind the same extractor interface.

## Versioning discipline (`CONFIRMED`)

Every extraction run pins: `extractor_version` (code/model identity), `extraction_config_version` (rule set / prompt+grammar/config), `schema_version`, and a fresh `extraction_run_id`. Re-running an old note under a new extractor version **never overwrites** the prior `SignalRecord` — it creates a new revision under the same `logical_signal_id`, and the old revision's `record_status` becomes `SUPERSEDED` only if a deliberate reprocessing decision says so (see D6 regression testing in `06-synthetic-data-design.md` and `11-testing-strategy.md`).

## What the extractor must handle correctly (`CONFIRMED` list, drives both D2 and D5 design and `11-testing-strategy.md`)

- **Negation** — "Customer is not increasing the order" must not become `direction=INCREASE`.
- **Conditionality** — "may increase volume if the promotion is approved" → `direction=INCREASE`, `business_certainty=POSSIBLE`, `conditionality=CONDITIONAL`, `condition_text="if the promotion is approved"` — never collapsed to a bare fact.
- **Uncertainty / hedging** — "customer indicated they might need additional inventory" → `business_certainty=POSSIBLE`, not `ASSERTED`.
- **Timing** — "next quarter", "in six weeks" normalized relative to `authored_at`, never relative to `extracted_at` or the current wall clock.
- **Entity association** — ambiguous or unresolved entities produce an **unresolved** mention rather than a guessed ID; forecast_key stays null.
- **Duplicate / contradictory signals** — near-identical notes about the same event, and later notes that reverse an earlier one ("previous expansion plan has been cancelled") are represented via `related_signal_ids`/`supersedes_signal_id`, not silently double-counted.
- **Stale references** — "same as last week" without restating the claim should not fabricate a fresh magnitude/date.
- **Unsupported inference** — a value must never appear in a field without a corresponding `evidence_ref`; this is measured directly as the "unsupported extraction rate" in `09-evaluation-plan.md`.

## Extraction error taxonomy (`CONFIRMED`, feeds `09-evaluation-plan.md` and `11-testing-strategy.md`)

False event · missed event · wrong entity · wrong direction · wrong magnitude · wrong timing · negation error · conditionality error · duplicate (double-counted) · missed supersession/stale signal · unsupported inference.
