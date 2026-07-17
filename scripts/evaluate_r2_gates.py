"""Evaluate the preregistered R2 gates from evaluation result files."""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.evaluation.dataset_loader import read_jsonl, write_json
from app.evaluation.metrics import evaluate_rows
from app.evaluation.r2_gates import evaluate_r2_gates
from app.evaluation.schemas import BenchmarkCase, EvaluationRunRow, GroundedAnswerAssessment


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--results", type=Path, nargs="+", required=True)
    parser.add_argument("--grounded-assessments", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    cases = read_jsonl(args.benchmark, BenchmarkCase)
    rows = [row for path in args.results for row in read_jsonl(path, EvaluationRunRow)]
    assessments = read_jsonl(args.grounded_assessments, GroundedAnswerAssessment)
    report = evaluate_r2_gates(evaluate_rows(rows, cases, assessments))
    write_json(args.output, report)
    print(f"R2 gates passed={report.passed}; wrote {args.output}")
    if not report.passed:
        raise SystemExit("R2 gates did not pass")


if __name__ == "__main__":
    main()
