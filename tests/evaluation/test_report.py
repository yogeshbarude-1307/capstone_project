import pytest

from dsfs.config import REPO_ROOT
from dsfs.evaluation.annotations import AnnotationDataset, load_dataset
from dsfs.evaluation.report import POC_CAVEAT, run_evaluation, write_bundle

from .conftest import make_case


def test_starter_run_is_reproducible_and_does_not_claim_gold():
    dataset = load_dataset(REPO_ROOT / "data/annotations/d2_starter.json")
    first = run_evaluation(dataset)
    second = run_evaluation(dataset)
    assert first == second
    report, predictions, quarantine = first
    assert report["provisional"] is True
    assert report["gold_mode"] is False
    assert report["natural_prevalence_available"] is False
    assert len(predictions) + len(quarantine) == 40
    assert report["views"][0]["metrics"]["actionable_event_detection"]["macro_f1"]["value"] is not None
    assert report["views"][0]["metrics"]["grounding"]["unsupported_inference_rate"]["value"] is not None
    with pytest.raises(ValueError, match="Gold mode"):
        run_evaluation(dataset, require_gold=True)


def test_bundle_persists_all_reproduction_artifacts_and_is_idempotent(tmp_path):
    dataset = AnnotationDataset(dataset_id="test", description="test", known_entities=["CUST-0001"], cases=[make_case()])
    destination = write_bundle(dataset, tmp_path)
    assert {p.name for p in destination.iterdir()} == {
        "report.json", "report.md", "dataset_snapshot.json", "predictions.jsonl", "quarantine.jsonl",
    }
    contents = {p.name: p.read_bytes() for p in destination.iterdir()}
    assert write_bundle(dataset, tmp_path) == destination
    assert contents == {p.name: p.read_bytes() for p in destination.iterdir()}
    assert POC_CAVEAT in (destination / "report.md").read_text(encoding="utf-8")
    (destination / "report.json").write_text("changed", encoding="utf-8")
    with pytest.raises(FileExistsError):
        write_bundle(dataset, tmp_path)


def test_samples_and_label_provenance_are_reported_separately():
    cases = [make_case("draft"), make_case("natural"), make_case("reviewed")]
    data = [c.model_dump() for c in cases]
    data[1]["sample"] = "natural_prevalence"
    data[2].update(label_origin="human", annotator_ids=["a", "b"], adjudication_state="agreed")
    dataset = AnnotationDataset(dataset_id="test", description="test", known_entities=["CUST-0001"], cases=data)
    report, _, _ = run_evaluation(dataset)
    assert len(report["views"]) == 3
    assert "overall_accuracy" not in report
    assert report["natural_prevalence_available"] is True


def test_scenarios_are_extracted_without_unrelated_history():
    dataset = load_dataset(REPO_ROOT / "data/annotations/d2_starter.json")
    _, predictions, _ = run_evaluation(dataset)
    by_source = {p.source_id: p for p in predictions}
    assert by_source["D2-038"].supersedes_signal_id == by_source["D2-037"].signal_id
    assert by_source["D2-039"].supersedes_signal_id is None
    assert by_source["D2-039"].validation_status.value == "REVIEW"


def test_reordered_input_produces_same_bundle(tmp_path):
    dataset = AnnotationDataset(dataset_id="test", description="test", known_entities=["CUST-0001"],
                                cases=[make_case("one"), make_case("two")])
    destination = write_bundle(dataset, tmp_path)
    reordered = dataset.model_copy(update={"cases": list(reversed(dataset.cases))})
    assert write_bundle(reordered, tmp_path) == destination


def test_gold_mode_accepts_reviewed_test_labels_and_reports_small_sample():
    cases = [make_case("one").model_dump(), make_case("two").model_dump()]
    for c in cases:
        c.update(split="test", label_origin="human", adjudication_state="agreed", annotator_ids=["a", "b"])
    dataset = AnnotationDataset(dataset_id="test-fixture", description="metric test only",
                                known_entities=["CUST-0001"], cases=cases)
    report, _, _ = run_evaluation(dataset, split="test", require_gold=True)
    assert report["gold_mode"] is True
    assert report["provisional"] is False
    assert report["below_proposed_size"] is True
