"""Export evidence-complete benchmark cases for human review without creating approvals."""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.evaluation.dataset_loader import read_jsonl, write_jsonl
from app.evaluation.schemas import BenchmarkCase, CaseType, NegativeReason
from app.evaluation.source_registry import SourceRegistry


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--source-registry", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--judge-assessments",
        type=Path,
        help="Optional completed judge JSONL. Its presence marks matching cases ready for review.",
    )
    return parser.parse_args()


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
    args = parse_args()
    cases = read_jsonl(args.candidates, BenchmarkCase)
    registry = SourceRegistry.load(args.source_registry)
    judged_case_ids = set()
    if args.judge_assessments and args.judge_assessments.exists():
        judged_case_ids = {
            payload["case_id"]
            for payload in read_jsonl(args.judge_assessments)
            if isinstance(payload.get("case_id"), str) and isinstance(payload.get("assessment"), dict)
        }
    records = []
    for case in sorted(cases, key=lambda item: item.case_id):
        sources = []
        for chunk_id in case.source_chunk_ids:
            source = registry.require(chunk_id)
            sources.append({
                "chunk_id": source.chunk_id,
                "ruleset": source.ruleset.value,
                "rule_number": source.rule_number,
                "source_path": source.source_path,
                "text": source.text,
            })
        records.append({
            "case_id": case.case_id,
            "case_hash": case.content_hash(),
            "review_state": "ready_for_human_review" if case.case_id in judged_case_ids else "awaiting_independent_judge",
            "query": case.query,
            "turns": [turn.model_dump(mode="json") for turn in case.turns],
            "language": case.language.value,
            "category": case.primary_category.value,
            "difficulty": case.difficulty.value,
            "expected_intent": case.expected_intent.value if case.expected_intent else None,
            "expected_route": case.expected_route.value if case.expected_route else None,
            "expected_rules": [reference.model_dump(mode="json") for reference in case.expected_rules],
            "answer_points": [point.model_dump(mode="json") for point in case.answer_points],
            "expected_tool_calls": [call.model_dump(mode="json") for call in case.expected_tool_calls],
            "negative_expectation": (
                case.negative_expectation.model_dump(mode="json") if case.negative_expectation else None
            ),
            "sources": sources,
            "review_template": {
                "reviewer_id": "<required>",
                "status": "approved|rejected",
                "verified_dimensions": _required_dimensions(case),
                "dimension_decisions": {name: True for name in _required_dimensions(case)},
                "verified_chunk_ids": list(case.source_chunk_ids),
                "notes": "<required for rejection or material caveat>",
                "second_review": False,
                "adjudicates_reviewers": [],
            },
        })
    write_jsonl(args.output, records)
    ready = sum(record["review_state"] == "ready_for_human_review" for record in records)
    print(f"Wrote {len(records)} review packet records; {ready} are ready for human review")


if __name__ == "__main__":
    main()
