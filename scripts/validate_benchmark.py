"""Validate benchmark candidates and export the human-approved accepted pool."""

import argparse
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.evaluation.benchmark_validator import BenchmarkValidator
from app.evaluation.dataset_loader import read_jsonl, write_jsonl
from app.evaluation.schemas import (
    BenchmarkCase,
    HumanReview,
    JudgeAssessment,
    ValidationRecord,
)
from app.evaluation.source_registry import SourceRegistry


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--source-registry", type=Path, required=True)
    parser.add_argument("--judge-assessments", type=Path, required=True)
    parser.add_argument("--human-reviews", type=Path, required=True)
    parser.add_argument("--validation-output", type=Path, required=True)
    parser.add_argument("--accepted-output", type=Path, required=True)
    parser.add_argument("--require-accepted", type=int, default=0)
    return parser.parse_args()


def _load_judges(path: Path) -> Dict[str, JudgeAssessment]:
    result: Dict[str, JudgeAssessment] = {}
    for payload in read_jsonl(path):
        case_id = payload.get("case_id")
        if not case_id or "assessment" not in payload:
            raise ValueError("judge records require case_id and assessment")
        if case_id in result:
            raise ValueError(f"duplicate judge assessment for {case_id}")
        result[case_id] = JudgeAssessment.model_validate(payload["assessment"])
    return result


def _load_human_reviews(path: Path) -> Dict[str, List[HumanReview]]:
    result: Dict[str, List[HumanReview]] = defaultdict(list)
    for payload in read_jsonl(path):
        case_id = payload.get("case_id")
        if not case_id or "review" not in payload:
            raise ValueError("human review records require case_id and review")
        result[case_id].append(HumanReview.model_validate(payload["review"]))
    return dict(result)


def main() -> None:
    args = parse_args()
    cases = read_jsonl(args.candidates, BenchmarkCase)
    registry = SourceRegistry.load(args.source_registry)
    judges = _load_judges(args.judge_assessments)
    reviews = _load_human_reviews(args.human_reviews)
    validator = BenchmarkValidator(registry)

    records: List[ValidationRecord] = []
    accepted_cases: List[BenchmarkCase] = []
    for case in sorted(cases, key=lambda item: item.case_id):
        record = validator.validate_case(
            case,
            accepted_cases=accepted_cases,
            judge_assessment=judges.get(case.case_id),
            human_reviews=reviews.get(case.case_id, []),
        )
        records.append(record)
        if record.accepted:
            accepted_cases.append(case)

    write_jsonl(args.validation_output, records)
    write_jsonl(args.accepted_output, accepted_cases)
    print(
        f"Validated {len(cases)} candidates: {len(accepted_cases)} accepted, "
        f"{len(cases) - len(accepted_cases)} rejected or pending"
    )
    if len(accepted_cases) < args.require_accepted:
        raise SystemExit(
            f"Accepted pool has {len(accepted_cases)} cases; "
            f"required at least {args.require_accepted}"
        )


if __name__ == "__main__":
    main()
