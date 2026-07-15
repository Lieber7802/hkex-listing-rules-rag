"""Freeze the deterministic-pass candidate pool before LLM judging."""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.evaluation.benchmark_validator import BenchmarkValidator
from app.evaluation.dataset_loader import read_jsonl, write_jsonl
from app.evaluation.schemas import BenchmarkCase, CheckStatus
from app.evaluation.source_registry import SourceRegistry


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--source-registry", type=Path, required=True)
    parser.add_argument("--validation-output", type=Path, required=True)
    parser.add_argument("--prejudge-output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    registry = SourceRegistry.load(args.source_registry)
    validator = BenchmarkValidator(registry)
    cases = []
    for path in sorted(args.input_dir.glob("part_*.jsonl")):
        cases.extend(read_jsonl(path, BenchmarkCase))
    records = [validator.validate_case(case) for case in cases]
    candidates = [
        case
        for case, record in zip(cases, records)
        if not any(check.status == CheckStatus.FAIL for check in record.checks)
    ]
    if len({case.case_id for case in candidates}) != len(candidates):
        raise ValueError("deterministic-pass pool contains duplicate case IDs")
    if len({case.content_hash() for case in candidates}) != len(candidates):
        raise ValueError("deterministic-pass pool contains duplicate full-case hashes")
    write_jsonl(args.validation_output, records)
    write_jsonl(args.prejudge_output, candidates)
    print(f"Deterministic pass pool: {len(candidates)}/{len(cases)} candidates")


if __name__ == "__main__":
    main()
