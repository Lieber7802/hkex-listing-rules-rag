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


def test_r2_profiles_make_legacy_and_optimized_behaviour_explicit():
    legacy = SYSTEM_CONFIGS["A1-legacy"]
    optimized = SYSTEM_CONFIGS["A1-new"]

    assert legacy.evidence_selection_policy == "legacy"
    assert legacy.tool_evidence_policy == "legacy"
    assert legacy.answer_evidence_contract == "legacy"
    assert optimized.evidence_selection_policy == "coverage_aware"
    assert optimized.tool_evidence_policy == "regulatory_grounded"
    assert optimized.answer_evidence_contract == "coverage_grounded"


def test_agentic_runner_passes_the_selected_r2_profile_to_the_orchestrator():
    runner = AgenticRAGRunner(SYSTEM_CONFIGS["A1-new"], _CapturingOrchestrator)

    rows = runner.run_case(answerable_case(), "r2-smoke")

    assert rows[0].system == "A1-new"
    assert runner._orchestrator().kwargs["evidence_selection_policy"] == "coverage_aware"
    assert runner._orchestrator().kwargs["tool_evidence_policy"] == "regulatory_grounded"
    assert runner._orchestrator().kwargs["answer_evidence_contract"] == "coverage_grounded"
