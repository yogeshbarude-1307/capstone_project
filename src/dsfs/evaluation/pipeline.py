"""CLI: python -m dsfs.evaluation.pipeline [--dataset PATH] [--split dev|test]."""

import argparse
from pathlib import Path

from dsfs.config import REPO_ROOT, get_settings
from dsfs.evaluation.annotations import load_dataset
from dsfs.evaluation.metrics import MetricConfig
from dsfs.evaluation.report import write_bundle


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=REPO_ROOT / "data" / "annotations" / "d2_starter.json")
    parser.add_argument("--output-dir", type=Path, default=get_settings().reports_dir / "extraction")
    parser.add_argument("--split", choices=("dev", "test"), default="dev")
    parser.add_argument("--require-gold", action="store_true")
    parser.add_argument("--magnitude-tolerance", type=float, default=1e-6)
    args = parser.parse_args()
    dataset = load_dataset(args.dataset)
    try:
        destination = write_bundle(dataset, args.output_dir, split=args.split, require_gold=args.require_gold,
                                   config=MetricConfig(magnitude_absolute_tolerance=args.magnitude_tolerance))
    except ValueError as exc:
        parser.error(str(exc))
    print(f"Extraction evaluation written to {destination}")
    print("Read report.md for results and label-provenance limits; report.json includes all denominators.")


if __name__ == "__main__":
    main()
