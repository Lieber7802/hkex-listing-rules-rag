from app.evaluation.runners import AgenticRAGRunner, SYSTEM_CONFIGS
from tests.evaluation_helpers import answerable_case


class _CapturingOrchestrator:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def process_query(self, query, **kwargs):
        return {
            "answer": "Rule 14.34 requires an announcement.",
            "retrieved_chunks": [],
            "citations": [],
            "route_decision": None,
            "tool_calls": [],
            "tool_results": [],
            "verification_result": None,
            "retrieval_rounds": [],
        }


def test_formal_r2_profiles_keep_production_policies_across_ablations():
    a1 = SYSTEM_CONFIGS["A1"]
    a2 = SYSTEM_CONFIGS["A2"]
    a3 = SYSTEM_CONFIGS["A3"]

    for config in (a1, a2, a3):
        assert config.evidence_selection_policy == "coverage_aware"
        assert config.tool_evidence_policy == "regulatory_grounded"
        assert config.answer_evidence_contract == "coverage_grounded"
    assert (a1.enable_tools, a1.enable_coverage_retry, a1.max_retrieval_rounds) == (True, True, 2)
    assert (a2.enable_tools, a2.enable_coverage_retry, a2.max_retrieval_rounds) == (True, False, 1)
    assert (a3.enable_tools, a3.enable_coverage_retry, a3.max_retrieval_rounds) == (False, True, 2)


def test_agentic_runner_passes_the_selected_r2_profile_to_the_orchestrator():
    runner = AgenticRAGRunner(SYSTEM_CONFIGS["A1"], _CapturingOrchestrator)

    rows = runner.run_case(answerable_case(), "r2-smoke")

    assert rows[0].system == "A1"
    assert runner._orchestrator().kwargs["evidence_selection_policy"] == "coverage_aware"
    assert runner._orchestrator().kwargs["tool_evidence_policy"] == "regulatory_grounded"
    assert runner._orchestrator().kwargs["answer_evidence_contract"] == "coverage_grounded"
