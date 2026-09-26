# 04 — API / Data Contracts

## Wire contracts (`CONFIRMED` approach, `PROPOSED` field lists)

Three JSON Schema documents are the canonical contracts for this POC (full text in `schemas/`):

- `schemas/source_evidence.schema.json`
- `schemas/signal_record.schema.json`
- `schemas/forecast_feature.schema.json`

Every stage of the pipeline validates its output against the relevant schema **before** writing it to the next store. A record that fails validation is quarantined (written to a `_rejected` table with the validation error attached), never silently coerced or dropped. Runtime validation uses Pydantic models generated from / kept in sync with these schemas; tabular batch checks (nulls, ranges, dtype) additionally use Pandera on the Parquet/DuckDB tables.

## Compatibility rules (`PROPOSED`)

**Current implementation:** Pydantic plus JSON Schema (with timestamp format
checking) validate evidence/signals. Rejected extraction rows persist in a
local `*_rejected.jsonl` file. Pandera/DuckDB batch validation and the access
interfaces below remain planned. Source-checkout/editable installation is the
supported workflow; canonical schemas are read from `docs/schemas/`.

- Additive optional field → minor schema-version bump, backward compatible.
- Enum expansion → minor bump, but every consumer must be checked against the new value before promotion.
- Semantic redefinition of an existing field, or removal/rename of a required field → major schema-version bump; old and new versions coexist in the ledger, never silently reinterpreted.
- `schema_version` is a required field on every record precisely so historical rows remain interpretable after a schema change.

## Local access interface (`PROPOSED` — this is what "serving" means for the POC)

No network service is required to satisfy the original brief's "machine-consumable, not manual file transfer" requirement in an offline POC — a stable, typed, versioned Python function that any other local process (e.g. a notebook, a script, a test) can call is sufficient and keeps the design consistent with the offline/local-only constraint.

```python
def get_features(
    entity_keys: list[str],
    forecast_cutoff: datetime,
    feature_set_version: str = "latest_approved",
) -> FeatureBatchResponse:
    """Batch point-in-time feature retrieval.

    Returns feature values plus, for every row: feature_definition_version,
    contributing_signal_ids, generated_at, feature_available_at, and a
    staleness_status. Never returns raw note text.
    """

def get_historical_features(
    entity_cutoff_pairs: list[tuple[str, datetime]],
    feature_set_version: str,
) -> pandas.DataFrame:
    """Reconstructs the feature table as it would have existed at each
    (entity, cutoff) pair, applying the point-in-time eligibility rule from
    03-data-model.md. This is the function the forecasting experiment harness
    calls to build arms B/C/D training data — it must never return a row
    whose contributing signal has available_at > cutoff."""
```

## Optional localhost HTTP wrapper (`PROPOSED`, build only if useful for the demo)

If a thin HTTP layer is added (e.g. FastAPI bound to `127.0.0.1` only, never `0.0.0.0`), it should expose:

| Endpoint | Purpose |
|---|---|
| `POST /v1/features:batchGet` | Latest eligible features for entity keys — wraps `get_features`. |
| `POST /v1/historical-features:retrieve` | Point-in-time features for entity/cutoff pairs — wraps `get_historical_features`. |
| `GET /v1/feature-sets/{version}` | Schema/feature names/types for a given `feature_definition_version`. |
| `GET /v1/lineage/{signal_id_or_feature_row_id}` | Resolves the full provenance chain back to source evidence. |
| `GET /health/live` | Process liveness only. |

This wrapper is explicitly optional (`OPEN` — see `14-open-questions.md`); the callable Python API above already satisfies every functional requirement of the POC and avoids the complexity of running/testing a network service inside an offline capstone environment.

## What is never exposed

The feature-access layer (Python function or HTTP wrapper) never returns `raw_text` from source evidence to a generic forecast consumer. Raw note access is restricted to the extraction pipeline, the gold-set annotation tooling, and lineage-trace debugging utilities — see `03-data-model.md` and `13-risks-and-dependencies.md` (data-handling risk, even for synthetic text, as a design habit worth carrying forward).
