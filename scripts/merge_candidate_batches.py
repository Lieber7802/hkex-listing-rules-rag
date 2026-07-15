"""Merge BenchmarkCase JSONL batches with schema, ID, and hash checks."""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.evaluation.dataset_loader import read_jsonl, write_jsonl
from app.evaluation.schemas import BenchmarkCase


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-count", type=int, required=True)
    args = parser.parse_args()
    cases_by_id = {}
    for path in sorted(args.input_dir.glob("part_*.jsonl")):
        for case in read_jsonl(path, BenchmarkCase):
            if case.case_id in cases_by_id:
                raise ValueError(f"duplicate candidate case_id: {case.case_id}")
            cases_by_id[case.case_id] = case
    if len(cases_by_id) != args.expected_count:
        raise ValueError(f"merged {len(cases_by_id)} cases; expected {args.expected_count}")
    cases = [cases_by_id[case_id] for case_id in sorted(cases_by_id)]
    if len({case.content_hash() for case in cases}) != len(cases):
        raise ValueError("candidate batches contain duplicate full-case content hashes")
    write_jsonl(args.output, cases)
    print(f"Merged {len(cases)} candidates to {args.output}")


if __name__ == "__main__":
    main()
