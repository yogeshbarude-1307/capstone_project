"""Milestone 2 acceptance test: "D0/D1 written to local storage; causal-
ordering assertion test passes." Also a reproducibility smoke test that
foreshadows the Milestone 9 reproducibility requirement (docs/09)."""

from __future__ import annotations

import json

import pandas as pd

from dsfs.contracts import validate_record
from dsfs.synth.config import GeneratorConfig
from dsfs.synth.generator import generate_dataset, write_dataset


def test_generate_dataset_produces_d0_and_d1():
    config = GeneratorConfig(seed=42, n_entities=8, n_weeks=26)
    dataset = generate_dataset(config)

    assert len(dataset.d0_demand) == 8 * 26
    assert len(dataset.d1_notes) > 0
    assert len(dataset.d1_notes) == len(dataset.d1_ground_truth)


def test_write_dataset_writes_all_four_local_files(tmp_path):
    config = GeneratorConfig(seed=42, n_entities=5, n_weeks=12)
    dataset = generate_dataset(config)
    paths = write_dataset(dataset, tmp_path)

    assert paths["d0_demand"].exists()
    assert paths["d1_notes"].exists()
    assert paths["d1_ground_truth"].exists()
    assert paths["generator_config"].exists()

    d0_reloaded = pd.read_parquet(paths["d0_demand"])
    assert len(d0_reloaded) == 5 * 12

    with paths["d1_notes"].open(encoding="utf-8") as f:
        note_lines = [json.loads(line) for line in f]
    assert len(note_lines) == len(dataset.d1_notes)
    for record in note_lines[:20]:
        validate_record("source_evidence", record)

    with paths["d1_ground_truth"].open(encoding="utf-8") as f:
        gt_lines = [json.loads(line) for line in f]
    assert len(gt_lines) == len(dataset.d1_ground_truth)


def test_no_filesystem_writes_outside_the_given_directory(tmp_path):
    """Offline/local-only sanity: write_dataset must only ever touch paths
    under the directory it's given (docs/05-technology-decision-matrix.md)."""
    config = GeneratorConfig(seed=1, n_entities=3, n_weeks=8)
    dataset = generate_dataset(config)
    target_dir = tmp_path / "raw"
    paths = write_dataset(dataset, target_dir)
    for p in paths.values():
        assert target_dir in p.parents


def test_same_seed_is_fully_reproducible():
    config = GeneratorConfig(seed=123, n_entities=6, n_weeks=30)
    d1 = generate_dataset(config)
    d2 = generate_dataset(config)

    pd.testing.assert_frame_equal(d1.d0_demand, d2.d0_demand)

    texts_1 = [n.raw_text for n in d1.d1_notes]
    texts_2 = [n.raw_text for n in d2.d1_notes]
    assert texts_1 == texts_2

    ids_1 = [n.source_id for n in d1.d1_notes]
    ids_2 = [n.source_id for n in d2.d1_notes]
    assert ids_1 == ids_2
    assert d1.d1_notes == d2.d1_notes
    assert d1.d1_ground_truth == d2.d1_ground_truth


def test_different_seeds_produce_different_demand():
    config_a = GeneratorConfig(seed=1, n_entities=6, n_weeks=30)
    config_b = GeneratorConfig(seed=2, n_entities=6, n_weeks=30)
    d1 = generate_dataset(config_a)
    d2 = generate_dataset(config_b)
    assert not d1.d0_demand["demand"].equals(d2.d0_demand["demand"])
