from pathlib import Path

from app.evaluation.reporting import export_report
from app.evaluation.runners import AgenticRAGRunner, SYSTEM_CONFIGS
from tests.evaluation_helpers import answerable_case


class FakeOrchestrator:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def process_query(self, query, **kwargs):
        return {
            "answer": "The issuer must publish an announcement.",
            "retrieved_chunks": [{"chunk_id": "chunk-main", "score": 1.0}],
            "citations": [{"chunk_id": "chunk-main", "document_id": "d", "source_path": "r"}],
            "route_decision": {"intent": "rule_lookup", "tool_decision": {"tool_mode": "tool_plus_retrieval"}},
            "tool_calls": [], "tool_results": [], "verification_result": {"unsupported_claims": []},
            "retrieval_rounds": [],
        }


def test_agentic_runner_records_ablation_configuration_and_case_row():
    case = answerable_case()
    rows = AgenticRAGRunner(SYSTEM_CONFIGS["A3"], FakeOrchestrator).run_case(case, "run-1")
    assert len(rows) == 1
    assert rows[0].system == "A3"
    assert rows[0].row_type.value == "single_turn"
    assert rows[0].answer


def test_agentic_runner_passes_explicit_index_path_to_orchestrator():
    index_path = Path("frozen-index")
    runner = AgenticRAGRunner(SYSTEM_CONFIGS["A1"], FakeOrchestrator, index_path=index_path)
    orchestrator = runner._orchestrator()
    assert orchestrator.kwargs["index_path"] == index_path


def test_report_export_writes_required_artifacts(tmp_path: Path):
    case = answerable_case()
    rows = AgenticRAGRunner(SYSTEM_CONFIGS["A1"], FakeOrchestrator).run_case(case, "run-1")
    summary = export_report(rows, [case], tmp_path)
    assert summary["systems"]["A1"]["case_count"] == 1
    for filename in (
        "summary.csv", "category_breakdown.csv", "language_breakdown.csv",
        "difficulty_breakdown.csv", "evaluation_report.md", "metric_readiness.json",
    ):
        assert (tmp_path / filename).is_file()
