"""Create explicit automated-only review records from reproducible audit inputs.

This command never creates a HumanReview.  It records the existing independent
LLM-judge decision for every selected case, and optionally adds a deterministic
tool-contract audit for tool cases.  The output is intended for
``validate_automated_review_release.py`` only.
"""

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.evaluation.dataset_loader import read_jsonl, write_jsonl
from app.evaluation.schemas import (
    AutomatedReview,
    BenchmarkCase,
    JudgeAssessment,
    ReviewStatus,
)
from app.tools.disclosure_checklist import DisclosureChecklistTool
from app.tools.size_test_calculator import SizeTestCalculatorTool
from app.tools.transaction_classifier import TransactionClassifierTool


JUDGE_REVIEWER_ID = "independent-llm-judge-deepseek-v4-flash"
JUDGE_REVIEW_PROTOCOL = "r2-independent-judge-attestation-v1"
TOOL_REVIEWER_ID = "deterministic-tool-contract-audit-v1"
TOOL_REVIEW_PROTOCOL = "r2-tool-contract-audit-v1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--judge-assessments", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--selected-judgements-output",
        type=Path,
        help="Optional exact-case subset of --judge-assessments for release freezing.",
    )
    parser.add_argument(
        "--include-tool-contract-audit",
        action="store_true",
        help="Recompute expected outputs for size-test and tool-chain cases.",
    )
    return parser.parse_args()


def _required_point_ids(case: BenchmarkCase) -> List[str]:
    return [
        point.point_id
        for point in [
            *case.answer_points,
            *(point for turn in case.turns for point in turn.answer_points),
        ]
        if point.required
    ]


def _load_judgements(path: Path) -> Dict[str, JudgeAssessment]:
    result: Dict[str, JudgeAssessment] = {}
    for row in read_jsonl(path):
        case_id = row.get("case_id")
        assessment = row.get("assessment")
        if not isinstance(case_id, str) or not isinstance(assessment, dict):
            raise ValueError("judge assessments require case_id and assessment")
        if case_id in result:
            raise ValueError(f"duplicate judge assessment for {case_id}")
        result[case_id] = JudgeAssessment.model_validate(assessment)
    return result


def _judge_review(case: BenchmarkCase, assessment: JudgeAssessment) -> AutomatedReview:
    if assessment.case_hash != case.content_hash():
        raise ValueError(f"judge assessment hash mismatch for {case.case_id}")
    passed = assessment.passes(_required_point_ids(case))
    return AutomatedReview(
        case_hash=case.content_hash(),
        reviewer_id=JUDGE_REVIEWER_ID,
        reviewer_kind="independent_llm_judge",
        review_protocol=JUDGE_REVIEW_PROTOCOL,
        review_model=assessment.judge_model,
        review_prompt_hash=assessment.judge_prompt_hash,
        status=ReviewStatus.APPROVED if passed else ReviewStatus.REJECTED,
        verified_dimensions=[
            "source_support",
            "expected_rules_valid",
            "answer_points_grounded",
            "category_fit",
            "difficulty_fit",
            "language_correct",
            "unsupported_claims",
        ],
        verified_chunk_ids=list(case.source_chunk_ids),
        notes=(
            "Independent LLM judge assessment satisfied the structured benchmark rubric. "
            "This is an automated assessment, not a human review."
            if passed
            else "Independent LLM judge assessment did not satisfy the structured benchmark rubric."
        ),
    )


def _values_match(actual: Any, expected: Any) -> bool:
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        return math.isclose(float(actual), float(expected), abs_tol=1e-8)
    if type(actual) is not type(expected):
        return False
    if isinstance(actual, dict):
        return set(actual) == set(expected) and all(
            _values_match(actual[key], expected[key]) for key in actual
        )
    if isinstance(actual, list):
        return len(actual) == len(expected) and all(
            _values_match(value, expected[index]) for index, value in enumerate(actual)
        )
    return actual == expected


def _tool_contract_review(case: BenchmarkCase) -> AutomatedReview:
    tools = {
        "size_test_calculator": SizeTestCalculatorTool(),
        "transaction_classifier": TransactionClassifierTool(),
        "disclosure_checklist": DisclosureChecklistTool(),
    }
    expected_sequence = (
        ["size_test_calculator"]
        if case.primary_category.value == "size_test_calculation"
        else ["size_test_calculator", "transaction_classifier", "disclosure_checklist"]
    )
    calls = case.expected_tool_calls
    errors: List[str] = []
    if [call.tool_name for call in calls] != expected_sequence:
        errors.append("expected tool sequence does not match category contract")
    if [call.order for call in calls] != list(range(1, len(calls) + 1)):
        errors.append("expected tool order is not consecutive")
    for call in calls:
        tool = tools.get(call.tool_name)
        if tool is None:
            errors.append(f"unsupported expected tool: {call.tool_name}")
            continue
        if not _values_match(tool.run(call.inputs), call.expected_output):
            errors.append(f"expected output differs from current {call.tool_name} result")
    if len(calls) == 3:
        size_call, classifier_call, checklist_call = calls
        if classifier_call.inputs.get("highest_ratio") != size_call.expected_output.get("highest_ratio"):
            errors.append("classifier input does not receive size-test highest_ratio")
        if checklist_call.inputs.get("classification") != classifier_call.expected_output.get("classification"):
            errors.append("checklist input does not receive classifier output")
        if checklist_call.inputs.get("shareholder_vote_required") != classifier_call.expected_output.get("shareholder_vote_required"):
            errors.append("checklist input does not receive shareholder vote requirement")
    return AutomatedReview(
        case_hash=case.content_hash(),
        reviewer_id=TOOL_REVIEWER_ID,
        reviewer_kind="deterministic_contract_audit",
        review_protocol=TOOL_REVIEW_PROTOCOL,
        review_model="python-deterministic-tool-audit",
        review_prompt_hash=hashlib.sha256(
            TOOL_REVIEW_PROTOCOL.encode("utf-8")
        ).hexdigest(),
        status=ReviewStatus.APPROVED if not errors else ReviewStatus.REJECTED,
        verified_dimensions=[
            "numeric_calculation",
            "tool_call_order",
            "tool_output_contract",
            "tool_chain_data_flow",
        ],
        verified_chunk_ids=list(case.source_chunk_ids),
        notes=(
            "Recomputed expected tool outputs and verified the declared tool-chain data flow. "
            "This is an automated assessment, not a human review."
            if not errors
            else "; ".join(errors)
        ),
    )


def build_automated_reviews(
    cases: Iterable[BenchmarkCase],
    judgements: Dict[str, JudgeAssessment],
    include_tool_contract_audit: bool,
) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for case in sorted(cases, key=lambda item: item.case_id):
        assessment = judgements.get(case.case_id)
        if assessment is None:
            raise ValueError(f"judge assessment is missing for {case.case_id}")
        reviews = [_judge_review(case, assessment)]
        if include_tool_contract_audit and case.primary_category.value in {
            "size_test_calculation",
            "tool_chain",
        }:
            reviews.append(_tool_contract_review(case))
        for review in reviews:
            records.append({
                "case_id": case.case_id,
                "automated_review": review.model_dump(mode="json"),
            })
    return records


def main() -> None:
    args = parse_args()
    cases = read_jsonl(args.candidates, BenchmarkCase)
    judgements = _load_judgements(args.judge_assessments)
    records = build_automated_reviews(
        cases,
        judgements,
        args.include_tool_contract_audit,
    )
    write_jsonl(args.output, records)
    if args.selected_judgements_output:
        write_jsonl(args.selected_judgements_output, [
            {
                "case_id": case.case_id,
                "assessment": judgements[case.case_id].model_dump(mode="json"),
            }
            for case in sorted(cases, key=lambda item: item.case_id)
        ])
    print(
        f"Wrote {len(records)} automated review records for {len(cases)} cases; "
        "no human expert review was performed"
    )


if __name__ == "__main__":
    main()
