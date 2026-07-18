import subprocess
import sys
from pathlib import Path

from app.evaluation.dataset_loader import read_jsonl, write_jsonl
from app.evaluation.schemas import EvaluationRunRow, GroundedAnswerAssessment, RowType
from tests.evaluation_helpers import answerable_case


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_answer_judge_cli_writes_one_assessment_per_case_level_result(tmp_path: Path):
    case = answerable_case()
    second_case = case.model_copy(update={"case_id": "case-second"})
    benchmark = tmp_path / "benchmark.jsonl"
    results = tmp_path / "results.jsonl"
    output = tmp_path / "grounded_assessments.jsonl"
    write_jsonl(benchmark, [case, second_case])
    write_jsonl(results, [
        EvaluationRunRow(
            run_id="r2-test",
            case_id=case.case_id,
            system="A1-new",
            row_type=RowType.SINGLE_TURN,
            query=case.query or "",
            answer="The issuer must publish an announcement.",
            citations=[{"chunk_id": "chunk-main"}],
            latency_seconds=1.0,
        ),
        EvaluationRunRow(
            run_id="r2-test",
            case_id=second_case.case_id,
            system="A1-new",
            row_type=RowType.SINGLE_TURN,
            query=second_case.query or "",
            answer="The issuer must publish an announcement.",
            citations=[{"chunk_id": "chunk-main"}],
            latency_seconds=1.0,
        ),
    ])

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/judge_evaluation_answers.py",
            "--benchmark", str(benchmark),
            "--results", str(results),
            "--output", str(output),
            "--backend", "deterministic",
            "--diagnostic",
            "--checkpoint-every", "1",
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assessments = read_jsonl(output, GroundedAnswerAssessment)
    assert len(assessments) == 2
    assert all(item.grounded_answer_completeness == 1.0 for item in assessments)
    assert "Checkpointed 1/2" in completed.stdout

    resumed = subprocess.run(
        [
            sys.executable,
            "scripts/judge_evaluation_answers.py",
            "--benchmark", str(benchmark),
            "--results", str(results),
            "--output", str(output),
            "--backend", "deterministic",
            "--diagnostic",
            "--resume",
            "--checkpoint-every", "1",
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert resumed.returncode == 0, resumed.stderr
    assert "Checkpointed" not in resumed.stdout
    assert len(read_jsonl(output, GroundedAnswerAssessment)) == 2


def test_answer_judge_cli_requires_an_explicit_diagnostic_flag_for_deterministic_mode(tmp_path: Path):
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/judge_evaluation_answers.py",
            "--benchmark", str(tmp_path / "benchmark.jsonl"),
            "--results", str(tmp_path / "results.jsonl"),
            "--output", str(tmp_path / "output.jsonl"),
            "--backend", "deterministic",
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode != 0
    assert "requires --diagnostic" in completed.stderr
