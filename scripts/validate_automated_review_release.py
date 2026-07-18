"""Validate an explicitly automated-only R2 review set without impersonating human review."""

import argparse
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.evaluation.dataset_loader import read_jsonl, write_jsonl
from app.evaluation.pre_review import static_checks_pass
from app.evaluation.schemas import (
    AutomatedReview,
    AutomatedValidationRecord,
    BenchmarkCase,
    CheckStatus,
    ValidationCheck,
    ValidationRecord,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--static-validation", type=Path, required=True)
    parser.add_argument("--automated-reviews", type=Path, required=True)
    parser.add_argument("--validation-output", type=Path, required=True)
    parser.add_argument("--accepted-output", type=Path, required=True)
    parser.add_argument("--require-accepted", type=int, default=0)
    return parser.parse_args()


def _load_static_validation(path: Path) -> Dict[str, ValidationRecord]:
    records = read_jsonl(path, ValidationRecord)
    result = {record.case_id: record for record in records}
    if len(result) != len(records):
        raise ValueError("static validation contains duplicate case IDs")
    return result


def _load_automated_reviews(path: Path) -> Dict[str, List[AutomatedReview]]:
    result: Dict[str, List[AutomatedReview]] = defaultdict(list)
    for payload in read_jsonl(path):
        case_id = payload.get("case_id")
        if not case_id or "automated_review" not in payload:
            raise ValueError("automated review records require case_id and automated_review")
        result[case_id].append(AutomatedReview.model_validate(payload["automated_review"]))
    return dict(result)


def _automated_check(reviews: List[AutomatedReview]) -> ValidationCheck:
    if not reviews:
        return ValidationCheck(
            check_name="automated_review",
            status=CheckStatus.FAIL,
            message="no automated agent review record is present",
        )
    rejected = [review.reviewer_id for review in reviews if review.status.value == "rejected"]
    pending = [review.reviewer_id for review in reviews if review.status.value == "pending"]
    if rejected:
        return ValidationCheck(
            check_name="automated_review",
            status=CheckStatus.FAIL,
            message="an automated agent rejected the case",
            details={"reviewers": rejected},
        )
    if pending:
        return ValidationCheck(
            check_name="automated_review",
            status=CheckStatus.PENDING,
            message="automated agent review is pending",
            details={"reviewers": pending},
        )
    return ValidationCheck(
        check_name="automated_review",
        status=CheckStatus.PASS,
        message="automated agent review approved; this is not human review",
        details={"reviewers": [review.reviewer_id for review in reviews]},
    )


def main() -> None:
    args = parse_args()
    cases = read_jsonl(args.candidates, BenchmarkCase)
    case_ids = {case.case_id for case in cases}
    if len(case_ids) != len(cases):
        raise ValueError("candidates contain duplicate case IDs")
    static_records = _load_static_validation(args.static_validation)
    reviews = _load_automated_reviews(args.automated_reviews)
    if set(reviews) != case_ids:
        raise ValueError("automated reviews must cover exactly the candidate cases")
    if not case_ids.issubset(static_records):
        missing = sorted(case_ids - set(static_records))
        raise ValueError(f"static validation is missing candidate cases: {missing}")

    records: List[AutomatedValidationRecord] = []
    accepted_cases: List[BenchmarkCase] = []
    for case in sorted(cases, key=lambda item: item.case_id):
        static = static_records[case.case_id]
        if static.case_hash != case.content_hash():
            raise ValueError(f"static validation hash mismatch for {case.case_id}")
        checks = [check for check in static.checks if check.check_name != "human_review"]
        if not static_checks_pass(static):
            checks.append(ValidationCheck(
                check_name="static_review_gate",
                status=CheckStatus.FAIL,
                message="one or more non-human static validation gates failed",
            ))
        checks.append(_automated_check(reviews[case.case_id]))
        record = AutomatedValidationRecord(
            case_id=case.case_id,
            case_hash=case.content_hash(),
            checks=checks,
            judge_assessment=static.judge_assessment,
            automated_reviews=reviews[case.case_id],
        )
        records.append(record)
        if record.accepted:
            accepted_cases.append(case)

    write_jsonl(args.validation_output, records)
    write_jsonl(args.accepted_output, accepted_cases)
    print(
        f"Automated-only validation: {len(accepted_cases)}/{len(cases)} accepted; "
        "no human expert review was performed"
    )
    if len(accepted_cases) < args.require_accepted:
        raise SystemExit(
            f"Accepted pool has {len(accepted_cases)} cases; "
            f"required at least {args.require_accepted}"
        )


if __name__ == "__main__":
    main()
