import pytest
from app.agents.langgraph_workflow_v2 import LangGraphOrchestratorV2, GraphNodes
from app.schemas.planning import RouteDecision, DecompositionPlan


class TestLangGraphWorkflowV2:
    
    def test_simple_query_skips_decomposition(self):
        nodes = GraphNodes(use_llm_planner=False)
        orch = LangGraphOrchestratorV2(use_llm_planner=False)
        
        result = orch.process_query("What is Rule 14A.35?", use_llm_planner=False)
        
        assert result["query_type"] == "direct"
        assert result["route_decision"] is not None
        route = RouteDecision(**result["route_decision"])
        assert route.requires_decomposition is False
        assert result["decomposition_plan"] is None
    
    def test_complex_query_requires_decomposition(self):
        orch = LangGraphOrchestratorV2(use_llm_planner=False)
        
        result = orch.process_query(
            "Compare disclosure requirements for connected and notifiable transactions",
            use_llm_planner=False
        )
        
        assert result["query_type"] == "multi_hop"
        assert result["route_decision"] is not None
        route = RouteDecision(**result["route_decision"])
        assert route.requires_decomposition is True
        assert route.intent == "comparison"
    
    def test_route_decision_contains_tool_info(self):
        orch = LangGraphOrchestratorV2(use_llm_planner=False)
        
        result = orch.process_query(
            "Calculate the size test ratio",
            use_llm_planner=False
        )
        
        assert result["route_decision"] is not None
        route = RouteDecision(**result["route_decision"])
        assert route.tool_decision.requires_tool is True
    
    def test_route_validation_warnings_generated(self):
        orch = LangGraphOrchestratorV2(use_llm_planner=False)
        
        result = orch.process_query(
            "Compare Rule 14A and Rule 14",
            use_llm_planner=False
        )
        
        assert result["route_validation"] is not None
    
    def test_decomposition_creates_subtasks(self):
        orch = LangGraphOrchestratorV2(use_llm_planner=False)
        
        result = orch.process_query(
            "Compare connected and notifiable transactions",
            use_llm_planner=False
        )
        
        if result["decomposition_plan"]:
            decomp = DecompositionPlan(**result["decomposition_plan"])
            assert len(decomp.subtasks) >= 2
    
    def test_workflow_with_heuristic_fallback(self):
        orch = LangGraphOrchestratorV2(use_llm_planner=False)
        
        result = orch.process_query(
            "What are the disclosure requirements?",
            use_llm_planner=False
        )
        
        assert result["route_decision"] is not None
        route = RouteDecision(**result["route_decision"])
        assert route.fallback_used is True
    
    def test_response_contains_all_new_fields(self):
        orch = LangGraphOrchestratorV2(use_llm_planner=False)
        
        result = orch.process_query("What is Rule 14A.35?", use_llm_planner=False)
        
        assert "route_decision" in result
        assert "decomposition_plan" in result
        assert "route_validation" in result
        assert "decomposition_validation" in result
        assert "confidence_level" in result


class TestIntegrationWithExistingComponents:
    
    def test_heuristic_planner_still_works(self):
        from app.agents.planner_agent import PlannerAgent
        
        planner = PlannerAgent()
        output = planner.plan("What is Rule 14A.35?")
        
        assert output.query_type == "direct"
        assert output.intent == "rule_lookup"
    
    def test_coverage_checker_works_with_new_state(self):
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
            answer_format="comparison_table"
        )
        
        from app.retrieval.hybrid_retriever import RetrievalResult
        from app.schemas.document import Chunk
        
        results = [
            RetrievalResult(
                chunk_id="c1",
                chunk=Chunk(
                    chunk_id="c1",
                    document_id="d1",
                    source_path="test.md",
                    text="Content A"
                ),
                score=0.9,
                bm25_score=0.9,
                dense_score=0.9
            )
        ]
        
        assessment = checker.assess(plan, results)
        
        assert assessment.needs_targeted_retrieval is True
        assert len(assessment.missing_information) > 0
