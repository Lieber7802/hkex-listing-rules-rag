"""Record an explicit task-owner approval for every benchmark case in a reviewed batch."""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.evaluation.dataset_loader import read_jsonl, write_jsonl
from app.evaluation.schemas import (
    BenchmarkCase,
    CaseType,
    HumanReview,
    NegativeReason,
    ReviewStatus,
)


def _required_dimensions(case: BenchmarkCase) -> list[str]:
    if case.case_type == CaseType.NEGATIVE and case.negative_expectation and case.negative_expectation.reason in {
        NegativeReason.NONEXISTENT_RULE,
        NegativeReason.INSUFFICIENT_TOOL_INPUTS,
        NegativeReason.AMBIGUOUS_QUERY,
        NegativeReason.OUT_OF_SCOPE,
    }:
        return ["expected_behavior"]
    if case.case_type == CaseType.TOOL and not case.source_chunk_ids:
        return ["tool_expectations"]
    return ["source_support", "rule_references"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reviewer-id", required=True)
    parser.add_argument("--notes", required=True)
    args = parser.parse_args()

    cases = read_jsonl(args.candidates, BenchmarkCase)
    reviews = []
    for case in cases:
        dimensions = _required_dimensions(case)
        reviews.append({
            "case_id": case.case_id,
            "review": HumanReview(
                case_hash=case.content_hash(),
                reviewer_id=args.reviewer_id,
                status=ReviewStatus.APPROVED,
                verified_dimensions=dimensions,
                dimension_decisions={dimension: True for dimension in dimensions},
                verified_chunk_ids=list(case.source_chunk_ids),
                notes=args.notes,
            ).model_dump(mode="json"),
        })
    write_jsonl(args.output, reviews)
    print(f"Recorded {len(reviews)} human approvals to {args.output}")


if __name__ == "__main__":
    main()
