import json

import pytest
from pydantic import ValidationError

from dsfs.config import REPO_ROOT
from dsfs.evaluation.annotations import AnnotatedCase, AnnotationDataset, load_dataset, snapshot_hash

from .conftest import make_case


def test_starter_is_explicitly_provisional_and_schema_matches_model():
    dataset = load_dataset(REPO_ROOT / "data/annotations/d2_starter.json")
    assert len(dataset.cases) == 40
    assert all(c.label_origin == "assistant_draft" and c.adjudication_state == "draft" for c in dataset.cases)
    assert all(c.split == "dev" and c.sample == "challenge" for c in dataset.cases)
    exported = json.loads((REPO_ROOT / "docs/annotations/d2_dataset.schema.json").read_text())
    assert exported == AnnotationDataset.model_json_schema()


def test_scenario_and_template_splits_cannot_leak():
    one, two = make_case("one"), make_case("two")
    two = two.model_copy(update={"split": "test", "template_group": one.template_group})
    with pytest.raises(ValidationError, match="crosses a split"):
        AnnotationDataset(dataset_id="test", description="test", known_entities=["CUST-0001"], cases=[one, two])


@pytest.mark.parametrize("changes, message", [
    ({"adjudication_state": "agreed"}, "cannot claim human adjudication"),
    ({"label_origin": "human", "adjudication_state": "agreed"}, "two distinct annotators"),
    ({"label_origin": "human", "adjudication_state": "resolved", "annotator_ids": ["a", "b"]}, "require an adjudicator"),
    ({"field_evidence": {}}, "needs evidence spans"),
])
def test_invalid_annotation_provenance_or_grounding_is_rejected(changes, message):
    data = make_case().model_dump() | changes
    with pytest.raises(ValidationError, match=message):
        AnnotatedCase.model_validate(data)


def test_content_hash_detects_edited_source_without_new_snapshot():
    data = make_case().model_dump()
    data["evidence"]["raw_text"] += " changed"
    with pytest.raises(ValidationError, match="content_hash"):
        AnnotatedCase.model_validate(data)


def test_snapshot_hash_is_independent_of_case_order_but_tracks_labels():
    dataset = AnnotationDataset(dataset_id="test", description="test", known_entities=["CUST-0001"],
                                cases=[make_case("one"), make_case("two")])
    reordered = dataset.model_copy(update={"cases": list(reversed(dataset.cases))})
    assert snapshot_hash(dataset) == snapshot_hash(reordered)
    revised = dataset.model_dump()
    revised["cases"][0]["expected"]["direction"] = "DECREASE"
    assert snapshot_hash(dataset) != snapshot_hash(AnnotationDataset.model_validate(revised))
