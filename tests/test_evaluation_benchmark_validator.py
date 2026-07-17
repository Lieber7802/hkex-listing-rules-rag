from datetime import date

from app.evaluation.benchmark_validator import BenchmarkValidator
from app.evaluation.schemas import (
    AnswerPoint,
    BenchmarkCase,
    CaseType,
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
)
from app.evaluation.source_registry import SourceRegistry, build_source_registry
from tests.evaluation_helpers import (
    SNAPSHOT_DATE,
    answerable_case,
    approved_review,
    passing_judge,
    provenance,
)


def _registry(path: str = "data/raw/rules/main_board.pdf") -> SourceRegistry:
    records, manifest, _ = build_source_registry(
        [
            {
                "chunk_id": "chunk-main",
                "document_id": "main-board",
                "source_path": path,
                "rule_number": "14.34",
                "chapter": "14",
                "section_title": "Notification and announcement",
                "text": (
                    "Main Board Rule 14.34 requires an issuer to publish an announcement "
                    "for a notifiable transaction and provide the required transaction details."
                ),
            }
        ],
        snapshot_date=SNAPSHOT_DATE,
        min_text_chars=20,
    )
    manifest = manifest.model_copy(update={
        "snapshot_id": "snapshot-001",
        "source_sha256": "1" * 64,
    })
    return SourceRegistry(records, manifest=manifest)


def _check(record, name):
    return next(check for check in record.checks if check.check_name == name)


def test_fully_validated_answerable_case_is_accepted():
    case = answerable_case()
    validator = BenchmarkValidator(_registry())

    record = validator.validate_case(
        case,
        judge_assessment=passing_judge(case),
        human_reviews=[approved_review(case)],
    )

    assert record.accepted is True
    assert all(check.status.value in {"pass", "not_applicable"} for check in record.checks)


def test_human_approval_is_mandatory_and_must_cover_required_dimensions():
    case = answerable_case()
    validator = BenchmarkValidator(_registry())

    missing = validator.validate_case(case, judge_assessment=passing_judge(case))
    wrong_scope = validator.validate_case(
        case,
        judge_assessment=passing_judge(case),
        human_reviews=[approved_review(case, dimensions=["language"])],
    )

    assert missing.accepted is False
    assert _check(missing, "human_review").status.value == "pending"
    assert wrong_scope.accepted is False
    assert _check(wrong_scope, "human_review").status.value == "fail"


def test_human_review_disagreement_requires_valid_adjudication():
    case = answerable_case()
    validator = BenchmarkValidator(_registry())
    rejected = HumanReview(
        case_hash=case.content_hash(),
        reviewer_id="reviewer-1",
        status=ReviewStatus.REJECTED,
        verified_dimensions=["source_support", "rule_references"],
        dimension_decisions={"source_support": False, "rule_references": False},
        verified_chunk_ids=list(case.source_chunk_ids),
    )
    approved = approved_review(case, reviewer_id="reviewer-2")
    approved.second_review = True

    unresolved = validator.validate_case(
        case,
        judge_assessment=passing_judge(case),
        human_reviews=[rejected, approved],
    )
    adjudicator = HumanReview(
        case_hash=case.content_hash(),
        reviewer_id="adjudicator",
        status=ReviewStatus.APPROVED,
        verified_dimensions=["source_support", "rule_references"],
        dimension_decisions={"source_support": True, "rule_references": True},
        verified_chunk_ids=list(case.source_chunk_ids),
        adjudicates_reviewers=["reviewer-1", "reviewer-2"],
    )
    resolved = validator.validate_case(
        case,
        judge_assessment=passing_judge(case),
        human_reviews=[rejected, approved, adjudicator],
    )

    assert unresolved.accepted is False
    assert _check(unresolved, "human_review").status.value == "fail"
    assert resolved.accepted is True


def test_second_review_requires_a_distinct_primary_reviewer():
    case = answerable_case()
    review = approved_review(case)
    review.second_review = True

    record = BenchmarkValidator(_registry()).validate_case(
        case,
        judge_assessment=passing_judge(case),
        human_reviews=[review],
    )

    assert record.accepted is False
    assert _check(record, "human_review").status.value == "fail"


def test_judge_must_be_independent_from_generator():
    case = answerable_case()
    record = BenchmarkValidator(_registry()).validate_case(
        case,
        judge_assessment=passing_judge(case, judge_model=case.provenance.generator_model),
        human_reviews=[approved_review(case)],
    )

    assert record.accepted is False
    assert _check(record, "judge_assessment").status.value == "fail"


def test_judge_and_human_reviews_are_bound_to_case_hash():
    original = answerable_case()
    modified = original.model_copy(update={"query": "A materially changed question"})
    validator = BenchmarkValidator(_registry())

    stale_judge = validator.validate_case(
        modified,
        judge_assessment=passing_judge(original),
        human_reviews=[approved_review(modified)],
    )
    stale_human = validator.validate_case(
        modified,
        judge_assessment=passing_judge(modified),
        human_reviews=[approved_review(original)],
    )

    assert _check(stale_judge, "judge_assessment").status.value == "fail"
    assert _check(stale_human, "human_review").status.value == "fail"


def test_judge_point_support_must_use_the_gold_evidence_mapping():
    case = answerable_case()
    assessment = passing_judge(case)
    assessment.answer_point_results[0].supporting_chunk_ids = ["chunk-not-mapped"]

    record = BenchmarkValidator(_registry()).validate_case(
        case,
        judge_assessment=assessment,
        human_reviews=[approved_review(case)],
    )

    assert record.accepted is False
    assert _check(record, "judge_assessment").status.value == "fail"


def test_human_source_approval_must_record_reviewed_chunks():
    case = answerable_case()
    review = approved_review(case)
    review.verified_chunk_ids = []

    record = BenchmarkValidator(_registry()).validate_case(
        case,
        judge_assessment=passing_judge(case),
        human_reviews=[review],
    )

    assert record.accepted is False
    assert _check(record, "human_review").status.value == "fail"


def test_archive_source_cannot_be_gold_evidence():
    case = answerable_case()
    validator = BenchmarkValidator(_registry("data/raw/archive/guidance_letters/old.pdf"))

    record = validator.validate_case(
        case,
        judge_assessment=passing_judge(case),
        human_reviews=[approved_review(case)],
    )

    assert record.accepted is False
    assert _check(record, "source_eligibility").status.value == "fail"


def test_case_snapshot_must_match_source_registry_manifest():
    case = answerable_case()
    case = case.model_copy(update={
        "provenance": case.provenance.model_copy(
            update={"source_snapshot_hash": "2" * 64}
        )
    })

    record = BenchmarkValidator(_registry()).validate_case(
        case,
        judge_assessment=passing_judge(case),
        human_reviews=[approved_review(case)],
    )

    assert record.accepted is False
    assert _check(record, "source_snapshot").status.value == "fail"


def test_near_duplicate_of_accepted_case_is_rejected():
    existing = answerable_case(case_id="existing")
    candidate = answerable_case(case_id="candidate")
    validator = BenchmarkValidator(_registry())

    record = validator.validate_case(
        candidate,
        accepted_cases=[existing],
        judge_assessment=passing_judge(candidate),
        human_reviews=[approved_review(candidate)],
    )

    assert record.accepted is False
    assert _check(record, "duplicate_detection").status.value == "fail"


def test_tool_case_recomputes_expected_output_with_tolerance():
    call = ExpectedToolCall(
        order=1,
        tool_name="size_test_calculator",
        inputs={
            "issuer_market_cap": 1000,
            "issuer_total_assets": 2000,
            "issuer_net_assets": 500,
            "issuer_annual_profit": 100,
            "issuer_shares_outstanding": 1000,
            "transaction_consideration": 200,
            "acquired_assets": 100,
            "acquired_profit": 10,
            "acquired_net_assets": 50,
            "consideration_shares": 0,
            "transaction_type": "acquisition",
        },
        expected_output={
            "highest_ratio": 20.0,
            "suggested_classification": "share_transaction",
        },
        numeric_tolerances={"highest_ratio": 0.01},
    )
    point = AnswerPoint(
        point_id="ratio",
        text="The highest ratio is 20%.",
        evidence_kind=EvidenceKind.TOOL,
        supporting_tool_call_orders=[1],
    )
    case = BenchmarkCase(
        case_id="tool-1",
        case_type=CaseType.TOOL,
        query="Calculate the size test for the supplied acquisition figures.",
        language=Language.ENGLISH,
        primary_category=PrimaryCategory.SIZE_TEST_CALCULATION,
        capability_tags=["tool"],
        difficulty=Difficulty.MEDIUM,
        as_of=SNAPSHOT_DATE,
        expected_intent=ExpectedIntent.CALCULATION_REQUIRED,
        expected_route=RouteMode.TOOL_ONLY,
        answer_points=[point],
        expected_tool_calls=[call],
        provenance=provenance(),
    )

    record = BenchmarkValidator(_registry()).validate_case(
        case,
        judge_assessment=passing_judge(case),
        human_reviews=[approved_review(case, dimensions=["tool_expectations"])],
    )

    assert record.accepted is True
    assert _check(record, "tool_expectations").status.value == "pass"


def test_nonexistent_rule_negative_case_does_not_require_source_support():
    case = BenchmarkCase(
        case_id="negative-1",
        case_type=CaseType.NEGATIVE,
        query="What is HKEX Rule 99Z.999?",
        language=Language.ENGLISH,
        primary_category=PrimaryCategory.NEGATIVE_INSUFFICIENT,
        capability_tags=["negative"],
        difficulty=Difficulty.HARD,
        as_of=date(2026, 7, 11),
        expected_intent=ExpectedIntent.RULE_LOOKUP,
        expected_route=RouteMode.TOOL_PLUS_RETRIEVAL,
        negative_expectation=NegativeExpectation(
            reason=NegativeReason.NONEXISTENT_RULE,
            expected_action=ExpectedAction.STATE_INSUFFICIENT_EVIDENCE,
            expected_message_points=["The rule was not found."],
        ),
        provenance=provenance(),
    )

    record = BenchmarkValidator(_registry()).validate_case(
        case,
        judge_assessment=passing_judge(case),
        human_reviews=[approved_review(case, dimensions=["expected_behavior"])],
    )

    assert record.accepted is True
    assert _check(record, "source_eligibility").status.value == "not_applicable"


def test_insufficient_tool_input_profile_checks_actual_missing_fields():
    case = BenchmarkCase(
        case_id="negative-tool",
        case_type=CaseType.NEGATIVE,
        query="Calculate the size test for a HKD 100m transaction.",
        language=Language.ENGLISH,
        primary_category=PrimaryCategory.NEGATIVE_INSUFFICIENT,
        capability_tags=["negative", "tool"],
        difficulty=Difficulty.HARD,
        as_of=SNAPSHOT_DATE,
        expected_intent=ExpectedIntent.CALCULATION_REQUIRED,
        expected_route=RouteMode.TOOL_ONLY,
        negative_expectation=NegativeExpectation(
            reason=NegativeReason.INSUFFICIENT_TOOL_INPUTS,
            expected_action=ExpectedAction.ASK_CLARIFICATION,
            target_tool_name="size_test_calculator",
            provided_tool_inputs={"transaction_consideration": 100},
            missing_inputs=["transaction_type"],
        ),
        provenance=provenance(),
    )

    record = BenchmarkValidator(_registry()).validate_case(
        case,
        judge_assessment=passing_judge(case),
        human_reviews=[approved_review(case, dimensions=["expected_behavior"])],
    )

    assert record.accepted is True
    assert _check(record, "case_type_profile").status.value == "pass"


def test_category_requires_matching_case_type_profile():
    case = answerable_case(category=PrimaryCategory.SIZE_TEST_CALCULATION)

    record = BenchmarkValidator(_registry()).validate_case(
        case,
        judge_assessment=passing_judge(case),
        human_reviews=[approved_review(case)],
    )

    check = _check(record, "case_type_profile")
    assert check.status.value == "fail"
    assert check.details == {
        "primary_category": "size_test_calculation",
        "expected_case_type": "tool",
        "actual_case_type": "answerable",
    }
