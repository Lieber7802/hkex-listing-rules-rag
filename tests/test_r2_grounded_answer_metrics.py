import json
from types import SimpleNamespace

from app.evaluation.answer_judge import GroundedAnswerJudge
from app.evaluation.metrics import evaluate_rows
from app.evaluation.schemas import EvaluationRunRow, ExpectedToolCall, RowType
from tests.evaluation_helpers import answerable_case


def _row(system: str, answer: str, citation_id: str) -> EvaluationRunRow:
    return EvaluationRunRow(
        run_id="r2-test",
        case_id="case-001",
        system=system,
        row_type=RowType.SINGLE_TURN,
        query="What does Main Board Rule 14.34 require?",
        answer=answer,
        citations=[{"chunk_id": citation_id}],
        retrieved_chunks=[{"chunk_id": citation_id}],
        latency_seconds=1.0,
    )


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


def test_evaluation_summary_uses_grounded_answer_assessments_as_primary_metric():
    case = answerable_case()
    rows = [
        _row("B3", "The issuer must publish an announcement.", "other-chunk"),
        _row("A1-new", "The issuer must publish an announcement.", "chunk-main"),
    ]
    judge = GroundedAnswerJudge(backend="deterministic")
    assessments = [judge.assess(case, row) for row in rows]

    summary = evaluate_rows(rows, [case], grounded_assessments=assessments)

    assert summary["systems"]["B3"]["grounded_answer_completeness"] == 0.0
    assert summary["systems"]["A1-new"]["grounded_answer_completeness"] == 1.0
    assert summary["paired_comparisons"]["A1-new_vs_B3"]["grounded_answer_completeness"]["mean_difference"] == 1.0


def test_llm_grounded_answer_judge_uses_semantic_correctness_with_deterministic_evidence_mapping():
    case = answerable_case()
    response = json.dumps({
        "point_assessments": [{
            "point_id": case.answer_points[0].point_id,
            "answered": True,
            "correct": True,
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
