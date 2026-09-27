"""Oracle features must key entity linkage off the generator's own ground truth
(docs/08), never off the rendered note's entity_mentions_raw — otherwise a
paraphrased or pronoun mention would silently break the oracle arm too.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from dsfs.forecast.oracle import build_oracle_features


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")


def test_oracle_uses_ground_truth_entity_key_not_rendered_mention(tmp_path: Path):
    """A note whose rendered mention is a pronoun/nickname (not the canonical
    entity_key) must still contribute to the correct entity's oracle features,
    because the oracle reads entity_key from ground truth, not the mention."""
    notes = [
        {
            "source_id": "n-1",
            "authored_at": "2026-01-05T09:00:00+00:00",
            "available_at": "2026-01-05T09:00:00+00:00",
            "entity_mentions_raw": ["they"],  # paraphrased — not resolvable by exact string match
        }
    ]
    gt = [
        {
            "source_id": "n-1",
            "entity_key": "CUST-0001",
            "direction": "INCREASE",
            "negated": False,
            "is_irrelevant": False,
            "effective_start": "2026-01-10T00:00:00+00:00",
            "effective_end": "2026-01-25T00:00:00+00:00",
            "stated_magnitude_value": 100,
            "stated_magnitude_unit": "units",
        }
    ]

    notes_path = tmp_path / "notes.jsonl"
    gt_path = tmp_path / "gt.jsonl"
    _write_jsonl(notes_path, notes)
    _write_jsonl(gt_path, gt)

    cutoff = datetime(2026, 1, 8, tzinfo=timezone.utc)
    df = build_oracle_features(
        gt_path, notes_path, cutoffs=[cutoff], entities=["CUST-0001", "CUST-0002"],
    )

    row_0001 = df[df["entity_key"] == "CUST-0001"].iloc[0]
    row_0002 = df[df["entity_key"] == "CUST-0002"].iloc[0]
    assert bool(row_0001["has_active_signal_30d"]) is True
    assert bool(row_0002["has_active_signal_30d"]) is False


def test_oracle_does_not_attribute_signal_to_wrong_entity(tmp_path: Path):
    notes = [
        {
            "source_id": "n-1",
            "authored_at": "2026-01-05T09:00:00+00:00",
            "available_at": "2026-01-05T09:00:00+00:00",
            "entity_mentions_raw": ["CUST-0002"],  # mention text disagrees with ground truth
        }
    ]
    gt = [
        {
            "source_id": "n-1",
            "entity_key": "CUST-0001",
            "direction": "DECREASE",
            "negated": False,
            "is_irrelevant": False,
            "effective_start": "2026-01-10T00:00:00+00:00",
            "effective_end": "2026-01-25T00:00:00+00:00",
            "stated_magnitude_value": None,
            "stated_magnitude_unit": None,
        }
    ]
    notes_path = tmp_path / "notes.jsonl"
    gt_path = tmp_path / "gt.jsonl"
    _write_jsonl(notes_path, notes)
    _write_jsonl(gt_path, gt)

    cutoff = datetime(2026, 1, 8, tzinfo=timezone.utc)
    df = build_oracle_features(
        gt_path, notes_path, cutoffs=[cutoff], entities=["CUST-0001", "CUST-0002"],
    )

    assert bool(df[df["entity_key"] == "CUST-0001"].iloc[0]["has_active_signal_30d"]) is True
    assert bool(df[df["entity_key"] == "CUST-0002"].iloc[0]["has_active_signal_30d"]) is False
