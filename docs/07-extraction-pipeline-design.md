> Historical design/evidence: the [realignment acceptance contract](20-realignment-acceptance.md) supersedes conflicting scope and semantics below. The current target is weekly customer demand, Monday UTC cutoffs, four separate weekly horizons, PASS-only published signals, required HTTP consumption, a one-hour simulated freshness target, and matched forecast-degradation lead time. Earlier test counts and results require revalidation.

# 07 — Extraction Pipeline Design

## Current implementation — rules baseline v0.2.0

The diagram below is the target design. The implemented path uses plain regex
rules and exact matching of **supplied** entity mentions against canonical IDs.
It does not run spaCy/statistical NER or a local LLM. Recognized deterministic
cues can populate semantic fields; missing/conflicting cues and unresolved
entities yield `NO_SIGNAL` or `REVIEW`. This is an explicit narrower baseline
than the originally proposed rules+NER degradation path, to be measured on D2
before deciding which additional extraction stage earns its complexity.

Calendar phrases use half-open intervals: “next month” is the next calendar
month, “next quarter” the next calendar quarter, and “next year” the next
calendar year. Synthetic naive timestamps are interpreted as UTC; aware
timestamps normalize to UTC. Unsupported phrases remain unnormalized.

Every run is a complete corpus interpretation. Physical IDs include source
revision, extractor/config version, and run ID; logical IDs retain the upstream
source identity. Repeated appends of identical physical records are idempotent;
different content under an existing ID is rejected before writing the batch.
The JSONL store is single-writer, without multi-process transactions.

Reconciliation considers only claims available when a reversal was authored.
A unique eligible prior claim for the same entity and compatible signal type
is linked with `supersedes_signal_id`; missing/ambiguous candidates remain
`REVIEW`. Links never read generator truth. Raw ledger rows remain unchanged:
`ledger_as_of` derives `SUPERSEDED` only once the reversal's source is available
at the requested cutoff. A run ID is required so alternate interpretations are
not counted together. Incremental cross-run reconciliation and near-duplicate
event clustering are not implemented; Milestone 5 must define their treatment.

Validation failures are appended beside the ledger to `*_rejected.jsonl`, with
source evidence, run identity, error, stage, and rejected signal when available.
Evidence references currently cover the whole note; fine-grained per-field
grounding and semantic accuracy remain evaluation work, not proven outcomes.
Enabling the unimplemented local-LLM stage fails explicitly.

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
