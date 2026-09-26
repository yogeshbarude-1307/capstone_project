"""Step 5 of the causal generation order (docs/06-synthetic-data-design.md):
orchestrate entities -> latent events -> notes -> demand, in that exact
order, and write D0/D1 to local storage.

generate_dataset() is pure (no I/O) so it can be tested and re-run cheaply.
write_dataset() is the only function that touches disk, and only ever
touches local paths under data/raw/ (docs/05-technology-decision-matrix.md —
offline/local-only constraint).

Independent randomness: three separate random.Random streams (latent, notes,
demand) are derived from one seed so the run is fully reproducible, while
note rendering and demand realization never share entropy — reinforcing
that demand realization is sampled independently of whatever notes turned
out to say (see tests/synth/test_leakage.py).
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from dsfs.config import Settings, get_settings
from dsfs.contracts import validate_record
from dsfs.models.source_evidence import SourceEvidence
from dsfs.synth.config import GeneratorConfig
from dsfs.synth.demand import realize_demand
from dsfs.synth.entities import generate_entities
from dsfs.synth.latent import generate_latent_events
from dsfs.synth.notes import NoteGroundTruth, generate_notes


@dataclass
class GeneratedDataset:
    config: GeneratorConfig
    entities: list[str]
    d0_demand: pd.DataFrame
    d1_notes: list[SourceEvidence]
    d1_ground_truth: list[NoteGroundTruth]

    def summary(self) -> dict:
        n_signal_notes = sum(1 for g in self.d1_ground_truth if not g.is_irrelevant)
        n_irrelevant = sum(1 for g in self.d1_ground_truth if g.is_irrelevant)
        n_reversal = sum(1 for g in self.d1_ground_truth if g.is_reversal)
        return {
            "n_entities": len(self.entities),
            "n_weeks": self.config.n_weeks,
            "n_demand_rows": len(self.d0_demand),
            "n_notes": len(self.d1_notes),
            "n_signal_notes": n_signal_notes,
            "n_irrelevant_notes": n_irrelevant,
            "n_reversal_notes": n_reversal,
            "irrelevant_fraction": n_irrelevant / len(self.d1_notes) if self.d1_notes else 0.0,
        }


def generate_dataset(config: GeneratorConfig) -> GeneratedDataset:
    rng_latent = random.Random(config.seed)
    rng_notes = random.Random(config.seed + 1)
    rng_demand = random.Random(config.seed + 2)

    entities = generate_entities(config)
    knowables, hidden_states = generate_latent_events(entities, config, rng_latent)

    # Step 3: render notes from Knowable only.
    evidence_rows, ground_truth_rows = generate_notes(knowables, config, rng_notes)

    # Step 4: realize demand from HiddenState only, independently, afterward.
    d0 = realize_demand(entities, hidden_states, config, rng_demand)

    return GeneratedDataset(
        config=config,
        entities=entities,
        d0_demand=d0,
        d1_notes=evidence_rows,
        d1_ground_truth=ground_truth_rows,
    )


def write_dataset(dataset: GeneratedDataset, raw_dir: Path) -> dict[str, Path]:
    # Fail before writing any artifact if evidence violates the wire contract.
    for note in dataset.d1_notes:
        validate_record("source_evidence", note.model_dump(mode="json"))
    raw_dir.mkdir(parents=True, exist_ok=True)

    d0_path = raw_dir / "d0_tabular_demand.parquet"
    dataset.d0_demand.to_parquet(d0_path, index=False)

    d1_notes_path = raw_dir / "d1_notes.jsonl"
    with d1_notes_path.open("w", encoding="utf-8") as f:
        for note in dataset.d1_notes:
            f.write(json.dumps(note.model_dump(mode="json")) + "\n")

    d1_ground_truth_path = raw_dir / "d1_note_ground_truth.jsonl"
    with d1_ground_truth_path.open("w", encoding="utf-8") as f:
        for gt in dataset.d1_ground_truth:
            f.write(json.dumps(gt.model_dump(mode="json")) + "\n")

    config_path = raw_dir / "generator_config.json"
    config_path.write_text(json.dumps(dataset.config.model_dump(mode="json"), indent=2), encoding="utf-8")

    return {
        "d0_demand": d0_path,
        "d1_notes": d1_notes_path,
        "d1_ground_truth": d1_ground_truth_path,
        "generator_config": config_path,
    }


def main(settings: Settings | None = None, config: GeneratorConfig | None = None) -> None:
    settings = settings or get_settings()
    config = config or GeneratorConfig()

    settings.ensure_dirs()
    dataset = generate_dataset(config)
    paths = write_dataset(dataset, settings.data_raw_dir)

    print("Synthetic dataset generated (Milestone 2):")
    for key, value in dataset.summary().items():
        print(f"  {key}: {value}")
    print("Written to:")
    for name, path in paths.items():
        print(f"  {name}: {path}")


if __name__ == "__main__":
    main()
