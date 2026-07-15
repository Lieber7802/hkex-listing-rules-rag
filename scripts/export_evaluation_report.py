"""Export reproducible CSV and Markdown evaluation reports from result JSONL files."""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.evaluation.dataset_loader import read_jsonl
from app.evaluation.reporting import export_report
from app.evaluation.schemas import BenchmarkCase, EvaluationRunRow


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--results", type=Path, nargs="+", required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("data/evaluation/reports"))
    args = parser.parse_args()
    cases = read_jsonl(args.benchmark, BenchmarkCase)
    rows = [row for path in args.results for row in read_jsonl(path, EvaluationRunRow)]
    export_report(rows, cases, args.output_dir)
    print(f"Wrote report to {args.output_dir}")


if __name__ == "__main__":
    main()
