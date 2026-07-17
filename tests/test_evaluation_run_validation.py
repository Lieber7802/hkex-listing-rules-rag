from app.evaluation.run_validation import (
    case_level_rows,
    validate_metric_readiness,
    validate_run_completeness,
)
from app.evaluation.schemas import (
    AnswerPoint,
    BenchmarkCase,
    BenchmarkTurn,
    CaseType,
    Difficulty,
    EvidenceKind,
    EvaluationRunRow,
    ExpectedIntent,
    Language,
    PrimaryCategory,
    RetrievalRoundRecord,
    RouteMode,
    RowType,
)
from tests.evaluation_helpers import SNAPSHOT_DATE, provenance


def _row(
    case_id="case-1",
    system="agentic_rag",
    row_type=RowType.SINGLE_TURN,
    **updates,
):
    payload = {
        "run_id": "run-1",
        "case_id": case_id,
        "system": system,
        "row_type": row_type,
        "query": "query",
        "answer": "answer",
        "latency_seconds": 0.1,
        "verification_result": {"unsupported_claims": []},
    }
    payload.update(updates)
    return EvaluationRunRow(**payload)


def _multi_case():
    point_one = AnswerPoint(
        point_id="p1",
        text="First supported point",
        evidence_kind=EvidenceKind.SOURCE,
        supporting_chunk_ids=["chunk-main"],
    )
    point_two = AnswerPoint(
        point_id="p2",
        text="Second supported point",
        evidence_kind=EvidenceKind.SOURCE,
        supporting_chunk_ids=["chunk-main"],
    )
    return BenchmarkCase(
        case_id="multi-1",
        case_type=CaseType.MULTI_TURN,
        language=Language.ENGLISH,
        primary_category=PrimaryCategory.MULTI_TURN_FOLLOW_UP,
        capability_tags=["multi_turn"],
        difficulty=Difficulty.HARD,
        as_of=SNAPSHOT_DATE,
        turns=[
            BenchmarkTurn(
                turn_index=1,
                query="What is a connected transaction?",
                expected_intent=ExpectedIntent.GENERAL,
                expected_route=RouteMode.RETRIEVAL,
                answer_points=[point_one],
            ),
            BenchmarkTurn(
                turn_index=2,
                query="What exemptions apply to it?",
                expected_intent=ExpectedIntent.GENERAL,
                expected_route=RouteMode.RETRIEVAL,
                answer_points=[point_two],
                depends_on_turn=1,
            ),
        ],
        source_chunk_ids=["chunk-main"],
        provenance=provenance(),
    )


def test_case_level_grain_does_not_double_count_turn_rows():
    rows = [
        _row(case_id="multi-1", row_type=RowType.TURN, turn_index=1),
        _row(case_id="multi-1", row_type=RowType.TURN, turn_index=2),
        _row(case_id="multi-1", row_type=RowType.AGGREGATE),
    ]

    assert len(case_level_rows(rows)) == 1
    assert validate_run_completeness(rows, ["multi-1"], ["agentic_rag"]) == {}


def test_run_completeness_reports_missing_and_duplicate_case_rows():
    rows = [
        _row(case_id="case-1"),
        _row(case_id="case-1"),
    ]
    issues = validate_run_completeness(
        rows,
        expected_case_ids=["case-1", "case-2"],
        systems=["agentic_rag"],
    )

    assert "missing case-level result: case-2" in issues["agentic_rag"]
    assert any("expected exactly one" in issue for issue in issues["agentic_rag"])


def test_coverage_metric_requires_round_level_coverage():
    incomplete = _row(
        retrieval_rounds=[
            RetrievalRoundRecord(
                round_number=1,
                queries=["query"],
                chunk_ids=["chunk-main"],
            )
        ]
    )
    complete = _row(
        coverage_before=0.2,
        coverage_after=0.8,
        retrieval_rounds=[
            RetrievalRoundRecord(
                round_number=1,
                queries=["query"],
                chunk_ids=["chunk-main"],
                coverage_before=0.2,
                coverage_after=0.8,
            )
        ],
    )

    assert validate_metric_readiness([incomplete])["coverage_improvement"].ready is False
    assert validate_metric_readiness([complete])["coverage_improvement"].ready is True


def test_claim_reduction_is_blocked_without_pre_post_answers():
    row = _row()
    readiness = validate_metric_readiness([row])

    assert readiness["unsupported_claim_detection"].ready is True
    assert readiness["unsupported_claim_reduction"].ready is False


def test_noise_sensitivity_requires_clean_perturbed_pair():
    clean = _row(case_id="case-1")
    orphan = _row(
        case_id="case-1-noise",
        perturbation_id="noise-1",
        parent_case_id="missing-parent",
    )
    paired = orphan.model_copy(update={"parent_case_id": "case-1"})

    assert validate_metric_readiness([clean, orphan])["noise_sensitivity"].ready is False
    assert validate_metric_readiness([clean, paired])["noise_sensitivity"].ready is True


def test_multi_turn_readiness_requires_turns_and_one_aggregate():
    case = _multi_case()
    incomplete = [_row(case_id="multi-1", row_type=RowType.AGGREGATE)]
    complete = [
        _row(case_id="multi-1", row_type=RowType.TURN, turn_index=1),
        _row(case_id="multi-1", row_type=RowType.TURN, turn_index=2),
        _row(case_id="multi-1", row_type=RowType.AGGREGATE),
    ]

    assert validate_metric_readiness(incomplete, [case])["multi_turn_resolution"].ready is False
    assert validate_metric_readiness(complete, [case])["multi_turn_resolution"].ready is True
