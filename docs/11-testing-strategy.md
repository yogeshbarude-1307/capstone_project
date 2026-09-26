# 11 — Testing Strategy

## Test families (`CONFIRMED` list)

| Family | Covers | Failure means |
|---|---|---|
| Schema/contract | Required fields, enums, nullability, extra-field rejection (`additionalProperties: false` on evidence/signal), cross-field invariants (e.g. `magnitude_value` implies `magnitude_unit`) | Contract is not actually enforceable |
| Extraction gold-set | Field-level precision/recall/F1 against D2 | Extractor is semantically unreliable |
| Hard-case / linguistic edge cases | The 5 hand-authored cases below plus D5 adversarial notes | Extractor only handles easy templates |
| Temporal / leakage | No historical PIT dataset row ever includes a signal with `available_at > forecast_cutoff` | Leakage — invalidates every downstream forecast result |
| Feature aggregation | Window boundaries, decay logic, duplicate/contradiction handling in the transformation layer | Feature semantics are unstable or double-counted |
| Local API contract | `get_features`/`get_historical_features` argument validation, batch behavior, versioning | Feature access is unreliable for the experiment harness |
| Forecast experiment | Rolling-origin correctness, identical config across arms A–D, ablation wiring | Business hypothesis test itself is invalid |
| Reprocessing / regression | D6 frozen set produces expected (or explicitly-diffed) output across extractor versions | Extractor changes silently rewrite history |
| Drift calibration | False-alert rate on no-drift windows; detection + lead time on D4 | Monitoring is too noisy or too slow to be useful |
| End-to-end | One full run: synthetic notes → signals → features → forecast comparison → report | Pipeline doesn't actually work together |

## Mandatory hand-authored hard cases (`CONFIRMED`, exact text and expected interpretation from the handoff)

| Note | Expected interpretation |
|---|---|
| "Customer is not increasing the order." | `direction=DECREASE` or `STABLE` is **wrong**; correct extraction recognizes the negated proposition and does **not** emit `direction=INCREASE`. Depending on final ontology mapping, expected output is `direction=STABLE` or `NA` with `negated=true`, never a positive assertion of increase. |
| "Customer may increase volume if the promotion is approved." | `signal_type=DEMAND_EXPECTATION`, `direction=INCREASE`, `business_certainty=POSSIBLE`, `conditionality=CONDITIONAL`, `condition_text="if the promotion is approved"`. |
| "Expected to increase orders next month." | `direction=INCREASE`, `business_certainty=EXPECTED`, `effective_start`/`effective_end` normalized to the month **after** `authored_at`, not the current wall-clock month. |
| "Previous expansion plan has been cancelled." | A new signal referencing/superseding the earlier expansion signal via `supersedes_signal_id`/`related_signal_ids`; the original expectation must not remain silently `ACTIVE`. |
| "Customer indicated they might need additional inventory." | `business_certainty=POSSIBLE` (hedged), not `ASSERTED`; `signal_type` likely `INVENTORY_POSITION` or `PURCHASE_INTENT` depending on final ontology mapping, with `impact_channel` correctly distinguishing this from a firm order. |

Expected labels come from the annotation rules in `06-synthetic-data-design.md` / the schema in `03-data-model.md` — these five cases are asserted directly as unit tests against the extractor, independent of the larger D2 statistical evaluation.

## Leakage test design (`CONFIRMED` requirement)

An explicit adversarial test constructs notes with `available_at` deliberately **after** a chosen forecast cutoff and asserts they are absent from `get_historical_features(..., cutoff)`'s contributing signals for that cutoff. A second test asserts that a note with `effective_start` in the future but `available_at` before cutoff **is** correctly included — confirming the eligibility rule isn't overcorrected into rejecting legitimate early signals.

## Reproducibility test (`CONFIRMED`)

Given the same pinned `schema_version` / `extractor_version` / `extraction_config_version` / `feature_definition_version` and the same D2/D3 snapshot, re-running the pipeline produces byte-identical (or numerically identical within a documented tolerance) signal and feature tables.
