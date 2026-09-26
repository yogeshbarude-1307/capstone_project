"""Milestone 1 acceptance tests (docs/12-implementation-milestones.md):

- contract round-trip: build a Pydantic object -> dump -> validate against
  the JSON Schema contract -> parse back into the same Pydantic type.
- schema validation demonstrably rejects a malformed record.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from dsfs.contracts import ContractValidationError, is_valid, validate_record
from dsfs.models import (
    EvidenceRef,
    ForecastFeatureRecord,
    SignalRecord,
    SourceEvidence,
)

ROUND_TRIP_CASES = [
    ("source_evidence", "valid_source_evidence", SourceEvidence),
    ("signal_record", "valid_signal_record", SignalRecord),
    ("forecast_feature", "valid_forecast_feature", ForecastFeatureRecord),
]


@pytest.mark.parametrize("contract_name,fixture_name,model_cls", ROUND_TRIP_CASES)
def test_round_trip(contract_name, fixture_name, model_cls, request):
    instance = request.getfixturevalue(fixture_name)

    dumped = instance.model_dump(mode="json")

    # Must validate cleanly against the canonical JSON Schema contract.
    validate_record(contract_name, dumped)
    assert is_valid(contract_name, dumped)

    # And must parse back into an equivalent Pydantic object.
    reparsed = model_cls.model_validate(dumped)
    assert reparsed.model_dump(mode="json") == dumped


def test_source_evidence_rejects_missing_required_field(valid_source_evidence):
    dumped = valid_source_evidence.model_dump(mode="json")
    del dumped["content_hash"]
    with pytest.raises(ContractValidationError):
        validate_record("source_evidence", dumped)
    assert not is_valid("source_evidence", dumped)


def test_source_evidence_rejects_unknown_field(valid_source_evidence):
    dumped = valid_source_evidence.model_dump(mode="json")
    dumped["not_a_real_field"] = "oops"
    with pytest.raises(ContractValidationError):
        validate_record("source_evidence", dumped)


def test_signal_record_rejects_bad_enum_value(valid_signal_record):
    dumped = valid_signal_record.model_dump(mode="json")
    dumped["direction"] = "SIDEWAYS"
    with pytest.raises(ContractValidationError):
        validate_record("signal_record", dumped)


def test_signal_record_pydantic_rejects_bad_enum_value(valid_signal_record):
    dumped = valid_signal_record.model_dump(mode="json")
    dumped["direction"] = "SIDEWAYS"
    with pytest.raises(ValidationError):
        SignalRecord.model_validate(dumped)


class TestBusinessRuleValidators:
    """These mirror the deterministic validator described in
    docs/07-extraction-pipeline-design.md: schema conformance is necessary
    but not sufficient, so cross-field business rules are enforced too."""

    def test_no_signal_requires_na_direction(self, valid_signal_record):
        data = valid_signal_record.model_dump()
        data["signal_type"] = "NO_SIGNAL"
        data["direction"] = "INCREASE"  # contradicts NO_SIGNAL
        with pytest.raises(ValidationError, match="NO_SIGNAL requires direction=NA"):
            SignalRecord.model_validate(data)

    def test_no_signal_with_na_direction_is_valid(self, valid_signal_record):
        data = valid_signal_record.model_dump()
        data["signal_type"] = "NO_SIGNAL"
        data["direction"] = "NA"
        data["magnitude_value"] = None
        data["magnitude_unit"] = None
        SignalRecord.model_validate(data)  # should not raise

    def test_magnitude_value_requires_unit(self, valid_signal_record):
        data = valid_signal_record.model_dump()
        data["magnitude_value"] = 500
        data["magnitude_unit"] = None
        with pytest.raises(ValidationError, match="magnitude_unit is missing"):
            SignalRecord.model_validate(data)

    def test_effective_end_cannot_precede_effective_start(self, valid_signal_record):
        data = valid_signal_record.model_dump()
        data["effective_start"] = "2026-03-01T00:00:00Z"
        data["effective_end"] = "2026-02-01T00:00:00Z"
        with pytest.raises(ValidationError, match="effective_end must not precede"):
            SignalRecord.model_validate(data)

    def test_evidence_ref_end_cannot_precede_start(self):
        with pytest.raises(ValidationError, match="char_end must be >= char_start"):
            EvidenceRef(source_id="ev-0001", char_start=10, char_end=2)

    def test_available_at_cannot_precede_authored_at(self, valid_source_evidence):
        data = valid_source_evidence.model_dump()
        data["authored_at"] = "2026-01-05T09:00:00Z"
        data["available_at"] = "2026-01-04T09:00:00Z"  # before it was even written
        with pytest.raises(ValidationError, match="available_at must not be earlier than authored_at"):
            SourceEvidence.model_validate(data)
