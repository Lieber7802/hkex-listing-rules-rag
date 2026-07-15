from datetime import date
from typing import List, Optional

from app.evaluation.schemas import (
    AnswerPoint,
    AnswerPointJudgeResult,
    BenchmarkCase,
    CaseType,
    CheckStatus,
    Difficulty,
    EvidenceKind,
    ExpectedIntent,
    GenerationProvenance,
    HumanReview,
    JudgeAssessment,
    Language,
    PrimaryCategory,
    ReviewStatus,
    RouteMode,
    RuleReference,
    RuleSet,
    ValidationCheck,
    ValidationRecord,
)


SNAPSHOT_DATE = date(2026, 7, 11)


def provenance(generator_model: str = "generator-model") -> GenerationProvenance:
    return GenerationProvenance(
        generator_model=generator_model,
        generator_prompt_hash="2" * 64,
        source_snapshot_id="snapshot-001",
        source_snapshot_hash="1" * 64,
        random_seed=42,
    )


def answerable_case(
    case_id: str = "case-001",
    query: str = "What does Main Board Rule 14.34 require?",
    chunk_id: str = "chunk-main",
    rule_number: str = "14.34",
    language: Language = Language.ENGLISH,
    category: PrimaryCategory = PrimaryCategory.RULE_LOOKUP,
    difficulty: Difficulty = Difficulty.EASY,
) -> BenchmarkCase:
    rule = RuleReference(
        ruleset=RuleSet.MAIN_BOARD,
        rule_number=rule_number,
        supporting_chunk_ids=[chunk_id],
    )
    point = AnswerPoint(
        point_id=f"{case_id}-point",
        text="The issuer must publish an announcement.",
        evidence_kind=EvidenceKind.SOURCE,
        supporting_chunk_ids=[chunk_id],
        supporting_rules=[rule],
    )
    return BenchmarkCase(
        case_id=case_id,
        case_type=CaseType.ANSWERABLE,
        query=query,
        language=language,
        primary_category=category,
        capability_tags=[],
        difficulty=difficulty,
        as_of=SNAPSHOT_DATE,
        expected_intent=ExpectedIntent.RULE_LOOKUP,
        expected_route=RouteMode.TOOL_PLUS_RETRIEVAL,
        answer_points=[point],
        expected_rules=[rule],
        source_chunk_ids=[chunk_id],
        provenance=provenance(),
    )


def passing_judge(
    case: BenchmarkCase,
    judge_model: str = "independent-judge",
) -> JudgeAssessment:
    point_ids: List[str] = [point.point_id for point in case.answer_points]
    for turn in case.turns:
        point_ids.extend(point.point_id for point in turn.answer_points)
    source_backed = bool(case.source_chunk_ids)
    rule_backed = bool(case.expected_rules) or any(
        point.supporting_rules for point in case.answer_points
    )
    return JudgeAssessment(
        case_hash=case.content_hash(),
        judge_model=judge_model,
        judge_prompt_hash="3" * 64,
        source_support=5 if source_backed else None,
        expected_rules_valid=5 if rule_backed else None,
        answer_points_grounded=5 if point_ids else None,
        category_fit=5,
        difficulty_fit=5,
        language_correct=True,
        no_unsupported_claims=True,
        answer_point_results=[
            AnswerPointJudgeResult(
                point_id=point_id,
                supported=True,
                supporting_chunk_ids=list(case.source_chunk_ids),
                reason="Supported by the mapped evidence.",
            )
            for point_id in point_ids
        ],
        issues=[],
        judge_reason="The annotation is grounded and correctly classified.",
    )


def approved_review(
    case: BenchmarkCase,
    reviewer_id: str = "reviewer-1",
    dimensions: Optional[List[str]] = None,
) -> HumanReview:
    verified_dimensions = dimensions or ["source_support", "rule_references"]
    return HumanReview(
        case_hash=case.content_hash(),
        reviewer_id=reviewer_id,
        status=ReviewStatus.APPROVED,
        verified_dimensions=verified_dimensions,
        dimension_decisions={name: True for name in verified_dimensions},
        verified_chunk_ids=list(case.source_chunk_ids),
    )


def accepted_validation(case: BenchmarkCase) -> ValidationRecord:
    judge = passing_judge(case)
    checks = []
    for name in (
        "schema",
        "source_snapshot",
        "language",
        "source_eligibility",
        "answer_point_mapping",
        "rule_references",
        "case_type_profile",
        "tool_expectations",
        "duplicate_detection",
        "judge_assessment",
        "human_review",
    ):
        checks.append(
            ValidationCheck(
                check_name=name,
                status=CheckStatus.PASS,
                message=f"{name} passed",
            )
        )
    return ValidationRecord(
        case_id=case.case_id,
        case_hash=case.content_hash(),
        checks=checks,
        judge_assessment=judge,
        human_reviews=[approved_review(case)],
    )
