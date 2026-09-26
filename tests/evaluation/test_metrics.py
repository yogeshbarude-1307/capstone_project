import pytest

from dsfs.evaluation.metrics import MetricConfig, evaluate
from dsfs.extraction.pipeline import QuarantinedRecord

from .conftest import make_case, make_prediction


def test_hand_computed_event_and_abstention_confusion_set():
    cases = [make_case("tp"), make_case("fn"), make_case("fp", no_signal=True), make_case("tn", no_signal=True)]
    predictions = [
        make_prediction(cases[0]),
        make_prediction(cases[1], signal_type="NO_SIGNAL", direction="NA", business_certainty="UNKNOWN"),
        make_prediction(cases[2], signal_type="DEMAND_EXPECTATION", direction="INCREASE", business_certainty="LIKELY"),
        make_prediction(cases[3]),
    ]
    result = evaluate(cases, predictions)
    events = result["actionable_event_detection"]["per_class"]["DEMAND_EXPECTATION"]
    assert (events["tp"], events["fp"], events["fn"]) == (1, 1, 1)
    assert events["f1"]["value"] == 0.5
    assert result["actionable_event_detection"]["macro_f1"]["value"] == 0.5
    assert result["signal_type"]["accuracy"]["value"] == 0.5
    abstention = result["abstention"]
    assert (abstention["tp"], abstention["fp"], abstention["fn"]) == (1, 1, 1)
    assert abstention["precision"]["value"] == abstention["recall"]["value"] == 0.5
    assert result["error_taxonomy"]["false_event"] == 1
    assert result["error_taxonomy"]["missed_event"] == 1


def test_missing_outputs_stay_in_denominators_and_are_not_correct_abstentions():
    result = evaluate([make_case("event"), make_case("empty", no_signal=True)], [])
    assert result["missing_output_count"] == 2
    assert result["fields"]["magnitude_value"]["accuracy"] == {"value": 0, "numerator": 0, "denominator": 2}
    assert result["abstention"]["recall"]["value"] == 0
    assert result["abstention"]["precision"]["value"] is None
    assert result["temporal"]["mean_interval_iou"]["value"] is None


def test_reviewed_candidate_is_not_an_actionable_event():
    case = make_case()
    result = evaluate([case], [make_prediction(case, validation_status="REVIEW")])
    assert result["fields"]["direction"]["accuracy"]["value"] == 1
    assert result["actionable_event_detection"]["per_class"]["DEMAND_EXPECTATION"]["fn"] == 1
    assert result["abstention"]["fp"] == 1


def test_duplicate_outputs_are_not_cherry_picked():
    case = make_case()
    predictions = [make_prediction(case), make_prediction(case, signal_id="another")]
    result = evaluate([case], predictions)
    assert result["duplicate_output_count"] == 1
    assert result["error_taxonomy"]["duplicate"] == 1
    event = result["actionable_event_detection"]["per_class"]["DEMAND_EXPECTATION"]
    assert (event["tp"], event["fp"], event["fn"]) == (0, 2, 1)


def test_wrong_value_is_unsupported_even_with_whole_note_citation():
    case = make_case(magnitude_value=15, magnitude_unit="%")
    result = evaluate([case], [make_prediction(case, magnitude_value=90)])
    assert result["grounding"]["evidence_span_coverage"]["value"] == 1
    assert result["error_taxonomy"]["wrong_magnitude"] == 1
    assert "magnitude_value" in result["errors"][0]["unsupported_fields"]
    assert result["grounding"]["unsupported_inference_rate"]["numerator"] == 1


def test_correct_value_without_covering_evidence_is_not_grounded():
    case = make_case(magnitude_value=15, magnitude_unit="%")
    prediction = make_prediction(case, evidence_ref=dict(source_id="one", char_start=0, char_end=4))
    result = evaluate([case], [prediction])
    assert result["fields"]["magnitude_value"]["accuracy"]["value"] == 1
    assert result["grounding"]["evidence_span_coverage"]["value"] == 0
    assert result["grounding"]["unsupported_inference_rate"]["value"] == 1


def test_magnitude_tolerance_and_unit_accuracy_are_separate():
    case = make_case(magnitude_value=15, magnitude_unit="%")
    result = evaluate([case], [make_prediction(case, magnitude_value=15.01, magnitude_unit="units")],
                      config=MetricConfig(magnitude_absolute_tolerance=0.02))
    assert result["fields"]["magnitude_value"]["accuracy"]["value"] == 1
    assert result["fields"]["magnitude_unit"]["accuracy"]["value"] == 0


def test_interval_iou_is_hand_computable_and_missing_time_is_zero():
    case = make_case(effective_start="2026-01-01T00:00:00Z", effective_end="2026-01-11T00:00:00Z")
    prediction = make_prediction(case, effective_start="2026-01-06T00:00:00Z", effective_end="2026-01-16T00:00:00Z")
    result = evaluate([case], [prediction])
    assert result["temporal"]["exact_match"]["value"] == 0
    assert result["temporal"]["mean_interval_iou"]["value"] == pytest.approx(1 / 3)
    assert evaluate([case], [make_prediction(case, effective_start=None, effective_end=None)])["temporal"]["mean_interval_iou"]["value"] == 0


def test_invalid_predictions_and_quarantine_cannot_inflate_accuracy():
    case = make_case()
    malformed = make_prediction(case).model_copy(update={"schema_version": "bad"})
    result = evaluate([case], [malformed])
    assert result["schema_valid_record_rate"]["value"] == 0
    assert result["fields"]["direction"]["accuracy"]["value"] == 0
    rejection = QuarantinedRecord("one", "invalid", "construct", case.evidence.model_dump(mode="json"), "test")
    result = evaluate([case], [], [rejection])
    assert result["model_validation_failure_rate"]["value"] == 1
    assert result["schema_valid_record_rate"]["value"] == 0


def test_out_of_bounds_citation_and_unknown_sources_are_detected():
    case = make_case()
    prediction = make_prediction(case, evidence_ref=dict(source_id="one", char_start=0, char_end=99999))
    assert evaluate([case], [prediction])["grounding"]["unsupported_inference_rate"]["value"] == 1
    with pytest.raises(ValueError, match="no D2 annotation"):
        evaluate([case], [make_prediction(make_case("unknown"))])


@pytest.mark.parametrize("tolerance", [-1, float("nan"), float("inf")])
def test_invalid_tolerance_is_rejected(tolerance):
    with pytest.raises(ValueError):
        MetricConfig(magnitude_absolute_tolerance=tolerance)


def test_unscored_fields_do_not_enter_classification_denominators():
    case = make_case().model_copy(update={"scored_fields": ["forecast_key"]})
    result = evaluate([case], [make_prediction(case, direction="DECREASE")])
    assert result["direction"]["accuracy"]["denominator"] == 0
    assert result["actionable_event_detection"]["macro_f1"]["value"] is None
    assert not result["errors"]


def test_schema_valid_cross_field_failure_is_counted_separately():
    case = make_case()
    prediction = make_prediction(case).model_copy(update={"magnitude_value": 15, "magnitude_unit": None})
    result = evaluate([case], [prediction])
    assert result["schema_valid_record_rate"]["value"] == 1
    assert result["semantic_cross_field_failure_rate"]["value"] == 1
    assert result["fields"]["direction"]["accuracy"]["value"] == 0


def test_wrong_source_revision_is_not_scored_as_correct():
    case = make_case()
    result = evaluate([case], [make_prediction(case, source_revision="r2")])
    assert result["lineage_failure_rate"]["value"] == 1
    assert result["fields"]["direction"]["accuracy"]["value"] == 0


def test_alternative_extraction_runs_cannot_be_combined():
    case = make_case()
    with pytest.raises(ValueError, match="one extraction run"):
        evaluate([case], [make_prediction(case), make_prediction(case, extraction_run_id="another")])
