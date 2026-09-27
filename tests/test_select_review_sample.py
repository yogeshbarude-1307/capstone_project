"""The human-review sample skeleton must be schema-valid and immediately
scorable by the existing M4 evaluation machinery with zero new scoring code.
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from dsfs.evaluation.annotations import AnnotationDataset
from dsfs.synth.config import GeneratorConfig
from dsfs.synth.entities import generate_entities
from dsfs.synth.generator import generate_dataset, write_dataset

from select_review_sample import select_sample  # noqa: E402


@pytest.fixture
def d1_dir(tmp_path: Path) -> Path:
    config = GeneratorConfig(seed=3, n_entities=5, n_weeks=52)
    dataset = generate_dataset(config)
    write_dataset(dataset, tmp_path)
    return tmp_path


def test_selected_sample_is_schema_valid(d1_dir: Path):
    result = select_sample(
        d1_dir / "d1_notes.jsonl", d1_dir / "generator_config.json", n=10, seed=1,
    )
    dataset = AnnotationDataset.model_validate(result)
    assert len(dataset.cases) == 10


def test_selection_is_deterministic_given_seed(d1_dir: Path):
    a = select_sample(d1_dir / "d1_notes.jsonl", d1_dir / "generator_config.json", n=10, seed=42)
    b = select_sample(d1_dir / "d1_notes.jsonl", d1_dir / "generator_config.json", n=10, seed=42)
    assert [c["evidence"]["source_id"] for c in a["cases"]] == [c["evidence"]["source_id"] for c in b["cases"]]


def test_placeholder_labels_mark_decision_no_signal(d1_dir: Path):
    result = select_sample(d1_dir / "d1_notes.jsonl", d1_dir / "generator_config.json", n=5, seed=1)
    for case in result["cases"]:
        assert case["expected"]["decision"] == "NO_SIGNAL"
        assert "REVIEWER_TODO" in case["expected"]["abstention_reason"]
        assert case["label_origin"] == "human"
        assert case["adjudication_state"] == "single"


def test_sample_smaller_than_requested_when_fewer_notes_exist(d1_dir: Path):
    result = select_sample(d1_dir / "d1_notes.jsonl", d1_dir / "generator_config.json", n=100000, seed=1)
    with (d1_dir / "d1_notes.jsonl").open() as f:
        n_notes = sum(1 for _ in f)
    assert len(result["cases"]) == n_notes
