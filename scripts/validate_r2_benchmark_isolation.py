"""Verify that an R2 benchmark is isolated from a frozen earlier release."""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.evaluation.dataset_loader import read_jsonl, write_json
from app.evaluation.r2_protocol import validate_benchmark_isolation
from app.evaluation.schemas import BenchmarkCase


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--reference-benchmark", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--duplicate-threshold", type=float, default=0.90)
    args = parser.parse_args()

    report = validate_benchmark_isolation(
        read_jsonl(args.benchmark, BenchmarkCase),
        read_jsonl(args.reference_benchmark, BenchmarkCase),
        duplicate_threshold=args.duplicate_threshold,
    )
    write_json(args.output, report)
    print(
        f"R2 isolation: passed={report.passed}, query_overlaps={report.query_overlap_count}, "
        f"multi_source_overlaps={report.multi_source_overlap_count}"
    )
    if not report.passed:
        raise SystemExit("R2 benchmark is not isolated from the reference release")


if __name__ == "__main__":
    main()
