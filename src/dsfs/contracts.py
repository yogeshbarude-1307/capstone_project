"""Loading and validating records against the canonical JSON Schema contracts.

The JSON Schema files in docs/schemas/ are the single source of truth for the
wire contracts (see docs/04-api-data-contracts.md). This module resolves them
from disk and exposes a small validation helper used by both tests and the
pipeline stages, so a record is always checked the same way regardless of
where in the pipeline it is produced.

A record that fails validation must never be silently coerced or dropped —
callers are expected to route validation failures to a quarantine table
(see docs/07-extraction-pipeline-design.md), not swallow the exception.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import jsonschema

# Repo root is three levels up from this file: src/dsfs/contracts.py -> repo root
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCHEMA_DIR = _REPO_ROOT / "docs" / "schemas"

SCHEMA_FILES: dict[str, str] = {
    "source_evidence": "source_evidence.schema.json",
    "signal_record": "signal_record.schema.json",
    "forecast_feature": "forecast_feature.schema.json",
}


class ContractValidationError(ValueError):
    """Raised when a record fails schema validation.

    Carries the offending record and the underlying jsonschema error so a
    caller can route it to a quarantine store with full diagnostic context,
    per the "never silently coerce or drop" rule in docs/04.
    """

    def __init__(self, contract_name: str, record: dict[str, Any], cause: jsonschema.ValidationError):
        self.contract_name = contract_name
        self.record = record
        self.cause = cause
        super().__init__(
            f"Record failed '{contract_name}' schema validation: {cause.message} "
            f"(path: {'/'.join(str(p) for p in cause.path)})"
        )


@lru_cache(maxsize=None)
def load_schema(contract_name: str) -> dict[str, Any]:
    """Load and cache a named JSON Schema contract from docs/schemas/."""
    if contract_name not in SCHEMA_FILES:
        raise KeyError(
            f"Unknown contract '{contract_name}'. Known contracts: {sorted(SCHEMA_FILES)}"
        )
    path = _SCHEMA_DIR / SCHEMA_FILES[contract_name]
    with path.open(encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=None)
def _validator_for(contract_name: str) -> jsonschema.protocols.Validator:
    schema = load_schema(contract_name)
    validator_cls = jsonschema.validators.validator_for(schema)
    validator_cls.check_schema(schema)
    return validator_cls(schema)


def validate_record(contract_name: str, record: dict[str, Any]) -> None:
    """Validate a plain-dict record against a named contract.

    Raises ContractValidationError on the first violation found. Callers
    that need every violation (e.g. a quarantine report) should use
    iter_validation_errors instead.
    """
    validator = _validator_for(contract_name)
    errors = sorted(validator.iter_errors(record), key=lambda e: e.path)
    if errors:
        raise ContractValidationError(contract_name, record, errors[0])


def iter_validation_errors(contract_name: str, record: dict[str, Any]):
    """Yield every jsonschema.ValidationError for a record (does not raise)."""
    validator = _validator_for(contract_name)
    yield from validator.iter_errors(record)


def is_valid(contract_name: str, record: dict[str, Any]) -> bool:
    """True/False convenience check, no exception raised."""
    validator = _validator_for(contract_name)
    return validator.is_valid(record)
