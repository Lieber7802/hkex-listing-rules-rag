import json
import hashlib
from types import SimpleNamespace

from app.evaluation.answer_judge import GroundedAnswerJudge
from app.evaluation.metrics import evaluate_rows
from app.evaluation.schemas import (
    AnswerPoint,
    EvaluationRunRow,
    EvidenceKind,
    ExpectedToolCall,
    GroundedAnswerAssessment,
    GroundedAnswerPointAssessment,
    RowType,
)
from tests.evaluation_helpers import answerable_case


def _row(system: str, answer: str, citation_id: str) -> EvaluationRunRow:
    return EvaluationRunRow(
        run_id="r2-test",
        case_id="case-001",
        system=system,
        row_type=RowType.SINGLE_TURN,
        query="What does Main Board Rule 14.34 require?",
        answer=answer,
        citations=[{
            "chunk_id": citation_id,
            "snippet": "Rule 14.34 requires an announcement as soon as possible.",
        }],
        retrieved_chunks=[{"chunk_id": citation_id}],
        latency_seconds=1.0,
    )


def _semantic_assessment(case, row, passed_by_point):
    return GroundedAnswerAssessment(
        run_id=row.run_id,
        case_id=row.case_id,
        system=row.system,
        answer_hash=hashlib.sha256(row.answer.encode("utf-8")).hexdigest(),
        judge_backend="llm:independent-judge",
        rubric_version="r2-grounded-answer-semantic-v2",
        point_assessments=[
            GroundedAnswerPointAssessment(
                point_id=point.point_id,
                answered=passed_by_point[index],
                correct=passed_by_point[index],
                grounded=True,
                reason="Mocked semantic decision.",
            )
            for index, point in enumerate(case.answer_points)
        ],
    )


def _case_with_points(case_id: str, point_count: int):
    case = answerable_case(case_id=case_id)
    return case.model_copy(update={
        "answer_points": [
            AnswerPoint(
                point_id=f"{case_id}-point-{index}",
                text=f"Required conclusion {index}.",
                evidence_kind=EvidenceKind.SOURCE,
                supporting_chunk_ids=["chunk-main"],
            )
            for index in range(point_count)
        ],
    })


def test_grounded_answer_judge_requires_both_answer_content_and_mapped_evidence():
    case = answerable_case()
    judge = GroundedAnswerJudge(backend="deterministic")

    supported = judge.assess(
        case,
        _row("A1-new", "The issuer must publish an announcement.", "chunk-main"),
    )
    unsupported = judge.assess(
        case,
        _row("B3", "The issuer must publish an announcement.", "other-chunk"),
    )

    assert supported.grounded_answer_completeness == 1.0
    assert supported.point_assessments[0].passed is True
    assert unsupported.grounded_answer_completeness == 0.0
    assert unsupported.point_assessments[0].grounded is False


def test_evaluation_summary_uses_semantic_grounded_assessments_as_primary_metric():
    case = answerable_case()
    rows = [
        _row("B3", "The issuer must publish an announcement.", "other-chunk"),
        _row("A1-new", "The issuer must publish an announcement.", "chunk-main"),
    ]
    assessments = [
        _semantic_assessment(case, rows[0], [False]),
        _semantic_assessment(case, rows[1], [True]),
    ]

    summary = evaluate_rows(rows, [case], grounded_assessments=assessments)

    assert summary["systems"]["B3"]["grounded_answer_completeness"] == 0.0
    assert summary["systems"]["A1-new"]["grounded_answer_completeness"] == 1.0
    assert summary["paired_comparisons"]["A1-new_vs_B3"]["grounded_answer_completeness"]["mean_difference"] == 1.0


def test_evaluation_summary_rejects_deterministic_assessments_for_formal_gac():
    case = answerable_case()
    row = _row("A1-new", "The issuer must publish an announcement.", "chunk-main")
    assessment = GroundedAnswerJudge(backend="deterministic").assess(case, row)

    summary = evaluate_rows([row], [case], grounded_assessments=[assessment])

    assert summary["systems"]["A1-new"]["grounded_answer_completeness"] is None
    assert summary["readiness"]["grounded_answer_completeness"]["ready"] is False
    assert any(
        "diagnostic" in reason
        for reason in summary["readiness"]["grounded_answer_completeness"]["reasons"]
    )


def test_llm_grounded_answer_judge_uses_semantic_correctness_with_deterministic_evidence_mapping():
    case = answerable_case()
    response = json.dumps({
        "point_assessments": [{
            "point_id": case.answer_points[0].point_id,
            "answered": True,
            "correct": True,
            "directly_supported": True,
            "overstated": False,
            "reason": "The wording correctly conveys the required announcement.",
        }]
    }) + "\nModel tail note that is not part of the JSON object."

    class _Completions:
        def __init__(self):
            self.kwargs = None

        def create(self, **kwargs):
            self.kwargs = kwargs
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=response))])

    completions = _Completions()
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    assessment = GroundedAnswerJudge(
        backend="llm", model="independent-judge", client=client,
    ).assess(
        case,
        _row("A1-new", "An HKEX announcement is required from the issuer.", "chunk-main"),
    )

    point = assessment.point_assessments[0]
    assert point.answered is True
    assert point.correct is True
    assert point.grounded is True
    assert assessment.grounded_answer_completeness == 1.0
    assert completions.kwargs["response_format"] == {"type": "json_object"}
    prompt = json.loads(completions.kwargs["messages"][1]["content"])
    mapped = prompt["answer_points"][0]["mapped_evidence"]["source_excerpts"]
    assert mapped == [{
        "chunk_id": "chunk-main",
        "text": "Rule 14.34 requires an announcement as soon as possible.",
    }]


def test_llm_judge_rejects_a_wrong_numeric_tool_answer_even_when_the_tool_succeeds():
    case = answerable_case().model_copy(update={
        "answer_points": [AnswerPoint(
            point_id="ratio",
            text="The highest size ratio is 18.0%.",
            evidence_kind=EvidenceKind.TOOL,
            supporting_tool_call_orders=[1],
        )],
        "expected_tool_calls": [ExpectedToolCall(
            order=1,
            tool_name="size_test_calculator",
            inputs={"transaction_consideration": 180, "transaction_type": "acquisition"},
            expected_output={"highest_ratio": 18.0},
        )],
    })
    response = json.dumps({"point_assessments": [{
        "point_id": "ratio",
        "answered": True,
        "correct": False,
        "directly_supported": True,
        "overstated": False,
        "reason": "The answer states 19.0%, not 18.0%.",
    }]})

    class _Completions:
        def create(self, **kwargs):
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=response))])

    client = SimpleNamespace(chat=SimpleNamespace(completions=_Completions()))
    row = _row("A1-new", "The highest size ratio is 19.0%.", "chunk-main").model_copy(update={
        "tool_calls": [{
            "call_id": "ratio-call",
            "tool_name": "size_test_calculator",
            "inputs": {"transaction_consideration": 180, "transaction_type": "acquisition"},
        }],
        "tool_results": [{
            "call_id": "ratio-call",
            "tool_name": "size_test_calculator",
            "success": True,
            "output": {"highest_ratio": 18.0},
        }],
    })

    assessment = GroundedAnswerJudge(backend="llm", client=client).assess(case, row)

    assert assessment.point_assessments[0].grounded is True
    assert assessment.point_assessments[0].correct is False
    assert assessment.grounded_answer_completeness == 0.0


def test_llm_judge_requires_direct_support_even_when_the_chunk_id_is_mapped():
    case = answerable_case()
    response = json.dumps({"point_assessments": [{
        "point_id": case.answer_points[0].point_id,
        "answered": True,
        "correct": True,
        "directly_supported": False,
        "overstated": False,
        "reason": "The cited text does not directly establish the asserted consequence.",
    }]})

    class _Completions:
        def create(self, **kwargs):
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=response))])

    client = SimpleNamespace(chat=SimpleNamespace(completions=_Completions()))
    row = _row("A1-new", "The issuer must publish an announcement.", "chunk-main")

    assessment = GroundedAnswerJudge(backend="llm", client=client).assess(case, row)

    assert assessment.point_assessments[0].correct is True
    assert assessment.point_assessments[0].grounded is False
    assert assessment.grounded_answer_completeness == 0.0


def test_llm_judge_fails_instead_of_lexically_falling_back_for_an_incomplete_response():
    case = answerable_case()
    response = json.dumps({"point_assessments": []})

    class _Completions:
        def create(self, **kwargs):
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=response))])

    client = SimpleNamespace(chat=SimpleNamespace(completions=_Completions()))

    try:
        GroundedAnswerJudge(backend="llm", client=client, max_attempts=1).assess(
            case,
            _row("A1-new", "The issuer must publish an announcement.", "chunk-main"),
        )
    except ValueError as exc:
        assert "must decide every requested point" in str(exc)
    else:
        raise AssertionError("incomplete LLM decisions must not fall back to lexical matching")


def test_gac_excludes_zero_answer_point_cases_from_its_denominator():
    scored_case = _case_with_points("scored", 1)
    zero_point_case = _case_with_points("zero", 0)
    scored_row = _row("A1-new", "Incorrect answer.", "chunk-main").model_copy(update={"case_id": "scored"})
    zero_row = _row("A1-new", "A response is present.", "chunk-main").model_copy(update={"case_id": "zero"})
    assessments = [
        _semantic_assessment(scored_case, scored_row, [False]),
        _semantic_assessment(zero_point_case, zero_row, []),
    ]

    summary = evaluate_rows(
        [scored_row, zero_row],
        [scored_case, zero_point_case],
        grounded_assessments=assessments,
    )

    metrics = summary["systems"]["A1-new"]
    assert metrics["grounded_answer_completeness"] == 0.0
    assert metrics["grounded_answer_passed_points"] == 0
    assert metrics["grounded_answer_scorable_points"] == 1


def test_gac_is_pooled_over_points_not_a_macro_average_over_cases():
    one_point_case = _case_with_points("one-point", 1)
    four_point_case = _case_with_points("four-point", 4)
    one_point_row = _row("A1-new", "A response.", "chunk-main").model_copy(update={"case_id": "one-point"})
    four_point_row = _row("A1-new", "A response.", "chunk-main").model_copy(update={"case_id": "four-point"})
    assessments = [
        _semantic_assessment(one_point_case, one_point_row, [True]),
        _semantic_assessment(four_point_case, four_point_row, [False, False, False, False]),
    ]

    summary = evaluate_rows(
        [one_point_row, four_point_row],
        [one_point_case, four_point_case],
        grounded_assessments=assessments,
    )

    metrics = summary["systems"]["A1-new"]
    assert metrics["grounded_answer_completeness"] == 0.2
    assert metrics["grounded_answer_passed_points"] == 1
    assert metrics["grounded_answer_scorable_points"] == 5


def test_evaluation_summary_keeps_the_report_container_when_tool_outputs_are_scored():
    case = answerable_case().model_copy(update={
        "expected_tool_calls": [ExpectedToolCall(
            order=1,
            tool_name="size_test_calculator",
            inputs={"transaction_consideration": 180, "transaction_type": "acquisition"},
            expected_output={"highest_ratio": 18.0},
        )],
    })
    rows = []
    assessments = []
    judge = GroundedAnswerJudge(backend="deterministic")
    for system in ("B3", "A1-new"):
        row = _row(system, "The issuer must publish an announcement.", "chunk-main").model_copy(update={
            "tool_calls": [{
                "call_id": f"{system}-call",
                "tool_name": "size_test_calculator",
                "inputs": {"transaction_consideration": 180, "transaction_type": "acquisition"},
            }],
            "tool_results": [{
                "call_id": f"{system}-call",
                "tool_name": "size_test_calculator",
                "success": True,
                "output": {"highest_ratio": 18.0},
            }],
        })
        rows.append(row)
        assessments.append(judge.assess(case, row))

    summary = evaluate_rows(rows, [case], grounded_assessments=assessments)

    assert set(summary["systems"]) == {"B3", "A1-new"}
    assert summary["systems"]["A1-new"]["tool_result_accuracy"] == 1.0
