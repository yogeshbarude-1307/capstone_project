# 03 — Canonical Data Model

**Status key:** `CONFIRMED` · `PROPOSED` · `OPEN` (see `00-development-requirements-spec.md`).

## Three-layer separation (`CONFIRMED`)

```
SOURCE EVIDENCE  →  STRUCTURED SIGNAL  →  FORECAST FEATURE
what was written    machine interpretation   model-ready input
```

These are never collapsed. A raw note, its extracted interpretation, and the numeric/categorical feature ultimately fed to the forecast model are three distinct, separately versioned objects, linked by ID.

## Temporal model — five clocks (`CONFIRMED`)

**Implementation convention (v0.2 baseline):** timestamps serialize in UTC;
naive synthetic input means UTC. Effective intervals are half-open `[start,
end)`. `available_at` lives on source evidence and is joined by physical
`source_id` plus verified `source_revision`, not inferred from `extracted_at`.
Offline historical replay reconstructs source knowledge at a cutoff; it does
not claim that today's extractor ran in the past. `ledger_as_of` selects one
explicit extraction run and derives supersession without mutating stored rows.

| Clock | Meaning |
|---|---|
| `source_event_time` | When the underlying real-world business event happened (may be null/unknown). |
| `authored_at` (a.k.a. `source_created_at`) | When the human wrote the note. |
| `available_at` | Earliest time the organization/system could actually have used the information — the **knowledge-time gate**. |
| `effective_start` / `effective_end` | The (possibly future) business period the note is talking about — the **effective demand period**. |
| `extracted_at` (a.k.a. `processed_at`) | When a specific extraction run interpreted the source. |
| `feature_available_at` (a.k.a. `feature_asof`) | The exact forecast cutoff / point-in-time at which the derived feature became usable. |

**Point-in-time (PIT) eligibility rule (`CONFIRMED`, non-negotiable):** for a forecast at cutoff `t`, a signal is eligible **iff**:

```
signal.available_at <= t
AND [signal.effective_start, signal.effective_end] intersects the target forecast horizon
AND signal.record_status == ACTIVE  (not superseded/retracted as of t)
```

A note may legitimately have `effective_start` **after** `t` — that is precisely what makes it an early signal. What must never happen is `available_at > t` for any signal used in a historical training/evaluation row. This is tested explicitly (see `11-testing-strategy.md`).

## Layer 1 — Source Evidence (`CONFIRMED` structure, `PROPOSED` field list)

| Field | Type | Notes |
|---|---|---|
| `source_id` | string/UUID | Immutable. |
| `source_type` | enum | `account_note`, `service_note`, `supplier_commentary`, `sales_commentary`, `other` (all synthetic in this POC). |
| `source_record_id` | string | Stable upstream identity (synthetic generator assigns it). |
| `source_revision` | string/int | Distinguishes edited versions of the same note. |
| `authored_at` | timestamp | See temporal model. |
| `available_at` | timestamp | See temporal model. |
| `raw_text` | string | The note text (evidence store only — not exposed to the forecast consumer by default). |
| `content_hash` | string | Hash of the exact text used, for reproducibility. |
| `entity_mentions_raw` | array\<string\> | Raw customer/product/etc. mentions as written (before resolution). |

Evidence rows are **immutable**. A correction to a note creates a new `source_revision`, never an in-place edit.

## Layer 2 — Structured Signal (`CONFIRMED` ontology, `PROPOSED` full field list)

### Signal ontology v0.1 (`CONFIRMED` — adopted from *Production Design.md* as the richest of the five source documents)

| `signal_type` | Typical subtypes | Forecast interpretation |
|---|---|---|
| `DEMAND_EXPECTATION` | increase, decrease, stable, volatile, unknown | Direct demand channel |
| `PURCHASE_INTENT` | exploring, planned, likely, contingent | Leading demand evidence |
| `ORDER_LIFECYCLE` | proposed, committed, confirmed, cancelled | Strong transactional evidence |
| `QUANTITY_REVISION` | increase, decrease, unchanged | Changes magnitude |
| `TIMING_REVISION` | accelerated, delayed, rescheduled | Redistributes demand across periods |
| `INVENTORY_POSITION` | low, high, adequate, stockout-risk | Potential demand driver |
| `COMMERCIAL_EVENT` | promotion, launch, discontinuation, pricing-change | Exogenous/known-event feature |
| `SUPPLY_FULFILLMENT` | shortage, allocation, capacity, lead-time-change | **Fulfillment channel — never auto-treated as demand** |
| `MARKET_CONTEXT` | competitor, macro, regulation, regional-event | Contextual predictor |
| `OTHER_RELEVANT` | free subtype, reviewed | Ontology-evolution candidate |

### Canonical signal fields (`PROPOSED`, trimmed from the full Production-Design schema to a POC-practical subset; R = required, O = optional/nullable)

| Field | R/O | Notes |
|---|---|---|
| `signal_id` | R | Immutable physical revision ID. |
| `logical_signal_id` | R | Stable identity across revisions/re-extractions. |
| `schema_version` | R | Ontology/schema version. |
| `signal_type` / `signal_subtype` | R | From ontology v0.1; `subtype` = `UNKNOWN` if not classifiable. |
| `direction` | R | `INCREASE / DECREASE / STABLE / MIXED / UNKNOWN / NA`. |
| `impact_channel` | R | `DEMAND / FULFILLMENT / MIX_ALLOCATION / UNKNOWN` — keeps supply notes from being silently read as demand. |
| `business_certainty` | R | `ASSERTED / EXPECTED / LIKELY / POSSIBLE / UNKNOWN` — what the **writer** conveys. |
| `conditionality` | R | `NONE / CONDITIONAL / UNKNOWN`. |
| `condition_text` | O | Grounded condition text, e.g. "if promotion approved". |
| `negated` | R | Boolean — explicit negation detected. |
| `magnitude_value` / `magnitude_low` / `magnitude_high` | O | Only populated when explicitly stated; never fabricated. |
| `magnitude_unit` / `magnitude_basis` | O | units/%/currency/etc.; `ABSOLUTE/DELTA/PERCENT/RANGE`. |
| `time_expression_raw` | O | Exact phrase, e.g. "next quarter". |
| `effective_start` / `effective_end` | O | Normalized effective period. |
| `entity_mentions` | R (may be empty) | Raw mentions carried from evidence. |
| `resolved_entities` | O | Canonical IDs after entity resolution (synthetic master data in this POC). |
| `forecast_key` | Derived | The forecasting entity key, once resolvable. |
| `evidence_ref` | R | Pointer + character offsets into the source evidence. |
| `extractor_version` / `extraction_config_version` / `extraction_run_id` | R | Full extraction provenance. |
| `validation_status` | R | `PASS / REVIEW / FAIL`. |
| `record_status` | R | `ACTIVE / SUPERSEDED / RETRACTED`. |
| `supersedes_signal_id` / `related_signal_ids` | O | Event history / conflict management. |

## Layer 3 — Forecast Feature (`PROPOSED`, evaluation-driven)

An initial candidate family to test in ablations — **none retained unless the ablation shows incremental value** (see `08-forecasting-experiment-design.md`):

| Family | Example feature |
|---|---|
| Presence/coverage | `has_active_signal_30d`, `signal_count_30d` |
| Direction | `net_demand_direction_30d` |
| Magnitude | `expected_qty_delta_next_horizon` |
| Commitments/cancellations | `committed_qty`, `cancelled_qty_30d` |
| Timing | `delay_count_90d`, `nearest_effective_start_days` |
| Recency | `days_since_latest_signal` |
| Confidence-weighted strength | counts by `business_certainty` class |
| Source diversity | `independent_source_count_30d` |
| Conflict | `active_conflict_count` |

Every feature row also carries `entity_key`, `forecast_cutoff`, `feature_definition_version`, `generated_at`, and the list of `signal_id`s that contributed to it (lineage).

## Provenance (`CONFIRMED` requirement, applies to every layer)

Every derived object must be traceable through: `forecast feature → contributing signal_id(s) → extractor_version/extraction_config_version → schema_version → source_revision → source_id`. This is implemented as columns on the row itself for the POC (no separate lineage service — see `05-technology-decision-matrix.md`).
