"""Merge independently written JudgeAssessment batches with completeness checks."""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.evaluation.dataset_loader import read_jsonl, write_jsonl
from app.evaluation.schemas import BenchmarkCase, JudgeAssessment


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-incomplete", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cases = read_jsonl(args.candidates, BenchmarkCase)
    cases_by_id = {case.case_id: case for case in cases}
    records_by_id = {}
    for path in sorted(args.input_dir.glob("part_*.jsonl")):
        for payload in read_jsonl(path):
            case_id = payload.get("case_id")
            if not isinstance(case_id, str) or "assessment" not in payload:
                raise ValueError(f"{path} contains a record without case_id and assessment")
            if case_id in records_by_id:
                raise ValueError(f"duplicate judge assessment for {case_id}")
            case = cases_by_id.get(case_id)
            if case is None:
                raise ValueError(f"judge assessment references unknown case {case_id}")
            assessment = JudgeAssessment.model_validate(payload["assessment"])
            if assessment.case_hash != case.content_hash():
                raise ValueError(f"judge assessment hash mismatch for {case_id}")
            records_by_id[case_id] = {
                "case_id": case_id,
                "assessment": assessment.model_dump(mode="json"),
            }
    missing = sorted(set(cases_by_id) - set(records_by_id))
    if missing and not args.allow_incomplete:
        raise ValueError(f"missing {len(missing)} judge assessments; first IDs: {missing[:10]}")
    ordered = [
        records_by_id[case.case_id]
        for case in cases
        if case.case_id in records_by_id
    ]
    write_jsonl(args.output, ordered)
    print(f"Merged {len(ordered)}/{len(cases)} judge assessments to {args.output}")


if __name__ == "__main__":
    main()
