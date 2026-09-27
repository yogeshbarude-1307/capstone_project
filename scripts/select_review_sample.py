"""Select a deterministic random sample of D1 notes for independent human
review (docs/16 Layer 2a), and emit a schema-valid, human-labelable skeleton
in the existing D2 AnnotationDataset format.

Reuses the Milestone-4 evaluation machinery unchanged: once a reviewer fills
in the ``expected``/``decision``/``field_evidence`` blanks, the sample scores
exactly like any other D2 dataset via the existing CLI:

    dsfs-evaluate --dataset data/annotations/human_review_sample.json --split dev

No new scoring code is written here — see docs/annotations/human_review_instructions.md.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from dsfs.config import REPO_ROOT, get_settings
from dsfs.synth.config import GeneratorConfig
from dsfs.synth.entities import generate_entities

_PLACEHOLDER_EXPECTED = {
    "signal_type": "NO_SIGNAL",
    "direction": "NA",
    "impact_channel": "UNKNOWN",
    "business_certainty": "UNKNOWN",
    "conditionality": "NONE",
    "condition_text": None,
    "negated": False,
    "magnitude_value": None,
    "magnitude_unit": None,
    "effective_start": None,
    "effective_end": None,
    "forecast_key": None,
    "supersedes_source_id": None,
    "decision": "NO_SIGNAL",
    "abstention_reason": "REVIEWER_TODO: read raw_text and replace this entire "
    "'expected' block with your own independent judgment, blind to the "
    "generator's ground truth and the extractor's output.",
}


def select_sample(
    notes_path: Path,
    config_path: Path,
    *,
    n: int = 50,
    seed: int = 20260927,
) -> dict:
    with notes_path.open(encoding="utf-8") as f:
        notes = [json.loads(line) for line in f if line.strip()]
    gen_config = GeneratorConfig.model_validate(
        json.loads(config_path.read_text(encoding="utf-8"))
    )
    known_entities = generate_entities(gen_config)

    rng = random.Random(seed)
    sample = rng.sample(notes, k=min(n, len(notes)))
    sample.sort(key=lambda n: n["source_id"])  # stable file ordering, independent of sampling order

    cases = []
    for note in sample:
        source_id = note["source_id"]
        cases.append({
            "evidence": note,
            "scenario_id": source_id,
            "template_group": source_id,
            "split": "dev",
            "sample": "natural_prevalence",
            "tags": [],
            "label_origin": "human",
            "annotator_ids": ["REVIEWER_TODO_REPLACE_WITH_YOUR_ID"],
            "adjudication_state": "single",
            "adjudicator_id": None,
            "ambiguity_flag": False,
            "expected": dict(_PLACEHOLDER_EXPECTED),
            "field_evidence": {},
        })

    return {
        "schema_version": "d2-0.1.0",
        "dataset_id": "human-review-sample-0.1.0",
        "description": (
            f"{len(cases)} notes selected deterministically (seed={seed}) from D1 for "
            "independent human review (docs/16 Layer 2a), blind to the generator's ground "
            "truth and the extractor's output. Placeholder expected labels must be replaced "
            "before scoring; see docs/annotations/human_review_instructions.md."
        ),
        "known_entities": known_entities,
        "cases": cases,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=50, help="Sample size")
    parser.add_argument("--seed", type=int, default=20260927, help="Sampling seed")
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "data" / "annotations" / "human_review_sample.json",
    )
    args = parser.parse_args()

    settings = get_settings()
    notes_path = settings.data_raw_dir / "d1_notes.jsonl"
    config_path = settings.data_raw_dir / "generator_config.json"
    for p in (notes_path, config_path):
        if not p.exists():
            parser.error(f"Required file missing: {p}. Run dsfs-generate first.")

    dataset = select_sample(notes_path, config_path, n=args.n, seed=args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(dataset, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    print(f"Selected {len(dataset['cases'])} notes for human review: {args.output}")
    print("Next: fill in each case's 'expected'/'decision'/'field_evidence' block, then run")
    print(f"  dsfs-evaluate --dataset {args.output} --split dev")


if __name__ == "__main__":
    main()
