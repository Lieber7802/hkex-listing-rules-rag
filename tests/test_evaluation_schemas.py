from datetime import date

import pytest
from pydantic import ValidationError

from app.evaluation.schemas import (
    AnswerPoint,
    BenchmarkCase,
    CaseType,
    CheckStatus,
    Difficulty,
    EvidenceKind,
    ExpectedAction,
    ExpectedIntent,
    ExpectedToolCall,
    HumanReview,
    Language,
    NegativeExpectation,
    NegativeReason,
    PrimaryCategory,
    ReviewStatus,
    RouteMode,
    RuleReference,
    RuleSet,
    ValidationCheck,
    ValidationRecord,
)
from tests.evaluation_helpers import accepted_validation, answerable_case, provenance


def test_source_answer_point_requires_exact_supporting_chunks():
    with pytest.raises(ValidationError, match="supporting_chunk_ids"):
        AnswerPoint(
            point_id="p1",
            text="A legal claim",
            evidence_kind=EvidenceKind.SOURCE,
        )


def test_tool_case_requires_expected_tool_calls():
    with pytest.raises(ValidationError, match="expected_tool_calls"):
        BenchmarkCase(
            case_id="tool-1",
            case_type=CaseType.TOOL,
            query="Calculate the ratio",
            language=Language.ENGLISH,
            primary_category=PrimaryCategory.SIZE_TEST_CALCULATION,
            difficulty=Difficulty.MEDIUM,
            as_of=date(2026, 7, 11),
            expected_intent=ExpectedIntent.CALCULATION_REQUIRED,
            expected_route=RouteMode.TOOL_ONLY,
            provenance=provenance(),
        )


def test_answer_point_rule_evidence_must_be_declared_by_case():
    point = AnswerPoint(
        point_id="p1",
        text="A supported claim",
        evidence_kind=EvidenceKind.SOURCE,
        supporting_chunk_ids=["chunk-declared"],
        supporting_rules=[
            RuleReference(
                ruleset=RuleSet.MAIN_BOARD,
                rule_number="14.34",
                supporting_chunk_ids=["chunk-undeclared"],
            )
        ],
    )

    with pytest.raises(ValidationError, match="chunk-undeclared"):
        BenchmarkCase(
            case_id="answerable-1",
            case_type=CaseType.ANSWERABLE,
            query="What does Rule 14.34 require?",
            language=Language.ENGLISH,
            primary_category=PrimaryCategory.RULE_LOOKUP,
            difficulty=Difficulty.EASY,
            as_of=date(2026, 7, 11),
            expected_intent=ExpectedIntent.RULE_LOOKUP,
            expected_route=RouteMode.RETRIEVAL,
            answer_points=[point],
            source_chunk_ids=["chunk-declared"],
            provenance=provenance(),
        )


def test_insufficient_input_negative_case_requires_target_tool():
    with pytest.raises(ValidationError, match="target_tool_name"):
        NegativeExpectation(
            reason=NegativeReason.INSUFFICIENT_TOOL_INPUTS,
            expected_action=ExpectedAction.ASK_CLARIFICATION,
            missing_inputs=["transaction_type"],
        )


def test_nonexistent_rule_cannot_require_source_backed_answer():
    point = AnswerPoint(
        point_id="p1",
        text="Unsupported answer",
        evidence_kind=EvidenceKind.SOURCE,
        supporting_chunk_ids=["chunk-1"],
    )
    with pytest.raises(ValidationError, match="cannot require source-backed"):
        BenchmarkCase(
            case_id="negative-1",
            case_type=CaseType.NEGATIVE,
            query="What is Rule 99Z.999?",
            language=Language.ENGLISH,
            primary_category=PrimaryCategory.NEGATIVE_INSUFFICIENT,
            difficulty=Difficulty.HARD,
            as_of=date(2026, 7, 11),
            expected_intent=ExpectedIntent.RULE_LOOKUP,
            expected_route=RouteMode.TOOL_PLUS_RETRIEVAL,
            answer_points=[point],
            source_chunk_ids=["chunk-1"],
            negative_expectation=NegativeExpectation(
                reason=NegativeReason.NONEXISTENT_RULE,
                expected_action=ExpectedAction.STATE_INSUFFICIENT_EVIDENCE,
            ),
            provenance=provenance(),
        )


def test_validation_record_recomputes_acceptance():
    record = ValidationRecord(
        case_id="case-1",
        case_hash="0" * 64,
        checks=[
            ValidationCheck(
                check_name="judge",
                status=CheckStatus.PENDING,
                message="judge pending",
            )
        ],
        human_reviews=[
            HumanReview(
                case_hash="0" * 64,
                reviewer_id="reviewer",
                status=ReviewStatus.APPROVED,
                verified_dimensions=["source_support", "rule_references"],
            )
        ],
        accepted=True,
    )
    assert record.accepted is False
    assert "judge pending" in record.rejection_reasons


def test_validation_record_rejects_stale_review_hash_on_revalidation():
    case = answerable_case()
    record = accepted_validation(case)
    record.human_reviews[0].case_hash = "f" * 64

    revalidated = ValidationRecord.model_validate(record.model_dump())

    assert revalidated.accepted is False
    assert any("review hashes" in reason for reason in revalidated.rejection_reasons)


def test_numeric_tolerances_must_be_non_negative():
    with pytest.raises(ValidationError, match="non-negative"):
        ExpectedToolCall(
            order=1,
            tool_name="size_test_calculator",
            inputs={},
            expected_output={"highest_ratio": 20.0},
            numeric_tolerances={"highest_ratio": -0.1},
        )
