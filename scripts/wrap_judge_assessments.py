"""Attach ordered candidate IDs to bare JudgeAssessment JSONL records."""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.evaluation.dataset_loader import read_jsonl, write_jsonl
from app.evaluation.schemas import BenchmarkCase, JudgeAssessment


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cases = read_jsonl(args.candidates, BenchmarkCase)
    assessments = read_jsonl(args.input, JudgeAssessment)
    if len(cases) != len(assessments):
        raise ValueError("candidate and assessment counts must match")
    records = []
    for case, assessment in zip(cases, assessments):
        if case.content_hash() != assessment.case_hash:
            raise ValueError(f"assessment hash mismatch for {case.case_id}")
        records.append({"case_id": case.case_id, "assessment": assessment.model_dump(mode="json")})
    write_jsonl(args.output, records)
    print(f"Wrapped {len(records)} judge assessments")


if __name__ == "__main__":
    main()
