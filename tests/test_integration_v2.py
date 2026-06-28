import pytest
from app.agents.langgraph_workflow_v2 import LangGraphOrchestratorV2, GraphNodes
from app.schemas.planning import RouteDecision, DecompositionPlan


class TestLangGraphWorkflowV2:
    def test_simple_query_is_direct(self):
        orch = LangGraphOrchestratorV2(use_llm_planner=False)

        result = orch.process_query("What is Rule 14A.35?", use_llm_planner=False)

        assert result["query_type"] == "direct"
        assert result["route_decision"] is not None
        route = RouteDecision(**result["route_decision"])
        assert route.query_type == "direct"
        assert route.sub_queries == ["What is Rule 14A.35?"]

    def test_complex_query_is_multi_hop(self):
        orch = LangGraphOrchestratorV2(use_llm_planner=False)

        result = orch.process_query(
            "Compare disclosure requirements for connected and notifiable transactions",
            use_llm_planner=False,
        )

        assert result["query_type"] == "multi_hop"
        assert result["route_decision"] is not None
        route = RouteDecision(**result["route_decision"])
        assert route.intent == "comparison"
        assert len(route.sub_queries) >= 2

    def test_route_decision_contains_tool_info(self):
        orch = LangGraphOrchestratorV2(use_llm_planner=False)

        result = orch.process_query("Calculate the size test ratio", use_llm_planner=False)

        assert result["route_decision"] is not None
        route = RouteDecision(**result["route_decision"])
        assert route.tool_decision.requires_tool is True

    def test_workflow_without_llm(self):
        orch = LangGraphOrchestratorV2(use_llm_planner=False)

        result = orch.process_query(
            "What are the disclosure requirements?",
            use_llm_planner=False,
        )

        assert result["route_decision"] is not None
        route = RouteDecision(**result["route_decision"])
        assert route.query_type is not None
        assert route.intent is not None

    def test_response_contains_all_expected_fields(self):
        orch = LangGraphOrchestratorV2(use_llm_planner=False)

        result = orch.process_query("What is Rule 14A.35?", use_llm_planner=False)

        assert "route_decision" in result
        assert "confidence_level" in result
        assert "citations" in result
        assert "tool_calls" in result
        assert "tool_results" in result

    def test_multi_hop_generates_sub_queries(self):
        orch = LangGraphOrchestratorV2(use_llm_planner=False)

        result = orch.process_query(
            "What are rules on connected transactions and notifiable transactions?",
            use_llm_planner=False,
        )

        route = RouteDecision(**result["route_decision"])
        assert len(route.sub_queries) >= 1


class TestIntegrationWithExistingComponents:
    def test_heuristic_planner_still_works(self):
        from app.agents.planner_agent import PlannerAgent

        planner = PlannerAgent()
        output = planner.plan("What is Rule 14A.35?")

        assert output.query_type == "direct"
        assert output.intent == "rule_lookup"

    def test_coverage_checker_works_with_planner_output(self):
        from app.agents.coverage_checker import CoverageChecker
        from app.schemas.query import PlannerOutput

        checker = CoverageChecker()
        plan = PlannerOutput(
            query_type="multi_hop",
            sub_queries=["A", "B"],
            needs_second_retrieval=True,
            reason="test",
            intent="comparison",
            sub_tasks=["A", "B"],
            retrieval_strategy="targeted_iterative",
            requires_tool=False,
            evidence_requirements={},
            answer_format="comparison_table",
        )

        from app.retrieval.hybrid_retriever import RetrievalResult
        from app.schemas.document import Chunk

        results = [
            RetrievalResult(
                chunk_id="c1",
                chunk=Chunk(
                    chunk_id="c1", document_id="d1", source_path="test.md", text="Content A"
                ),
                score=0.9,
                bm25_score=0.9,
                dense_score=0.9,
            )
        ]

        assessment = checker.assess(plan, results)

        assert assessment.needs_targeted_retrieval is True
        assert len(assessment.missing_information) > 0

    def test_route_decision_to_planner_output_conversion(self):
        route = RouteDecision(
            query_type="multi_hop",
            intent="comparison",
            retrieval_strategy="multi_query",
            sub_queries=["A?", "B?"],
        )

        po = route.to_planner_output()

        assert po.query_type == "multi_hop"
        assert po.sub_queries == ["A?", "B?"]
        assert po.retrieval_strategy == "multi_query"
