"""Select a fixed-seed benchmark from the validated pool using joint quotas."""

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.evaluation.dataset_loader import read_jsonl, write_json, write_jsonl
from app.evaluation.sampling import SamplingQuota, StratifiedSampler
from app.evaluation.schemas import BenchmarkCase, ValidationRecord


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accepted-pool", type=Path, required=True)
    parser.add_argument("--validation-records", type=Path, required=True)
    parser.add_argument("--quota", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest-output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cases = read_jsonl(args.accepted_pool, BenchmarkCase)
    records = read_jsonl(args.validation_records, ValidationRecord)
    with args.quota.open("r", encoding="utf-8") as handle:
        quota = SamplingQuota.model_validate(json.load(handle))
    selected, manifest = StratifiedSampler().select(cases, records, quota, args.seed)
    write_jsonl(args.output, selected)
    write_json(args.manifest_output, manifest)
    print(f"Selected {len(selected)} cases with seed {args.seed}")


if __name__ == "__main__":
    main()
