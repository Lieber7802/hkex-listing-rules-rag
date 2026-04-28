import pytest
from app.schemas.planning import RouteDecision, ToolDecision, DecompositionPlan, SubTask
from app.agents.llm_route_planner import LLMRoutePlanner
from app.agents.route_validator import HeuristicRouteValidator
from app.agents.task_decomposer import TaskDecomposer
from app.agents.decomposition_validator import DecompositionValidator


class TestLLMRoutePlanner:
    
    def test_simple_query_does_not_require_decomposition(self):
        planner = LLMRoutePlanner()
        result = planner.plan("What is Rule 14A.35?")
        
        assert isinstance(result, RouteDecision)
        assert result.query_type in ["direct", "multi_hop"]
        assert result.requires_decomposition is False
        assert result.retrieval_strategy == "single_pass"
    
    def test_comparison_query_requires_decomposition(self):
        planner = LLMRoutePlanner()
        result = planner.plan("Compare disclosure requirements for connected and notifiable transactions")
        
        assert isinstance(result, RouteDecision)
        assert result.query_type == "multi_hop"
        assert result.requires_decomposition is True
        assert result.intent == "comparison"
    
    def test_calculation_query_requires_tool(self):
        planner = LLMRoutePlanner()
        result = planner.plan("Calculate the size test ratio for this transaction")
        
        assert isinstance(result, RouteDecision)
        assert result.tool_decision.requires_tool is True
        assert result.tool_decision.tool_name in ["size_test_calculator", "SizeTestCalculator"]
    
    def test_fallback_on_llm_failure(self):
        planner = LLMRoutePlanner(llm_client=None)
        result = planner.plan("What is Rule 14A.35?")
        
        assert isinstance(result, RouteDecision)
        assert result.fallback_used is True
    
    def test_output_contains_validation_warnings(self):
        planner = LLMRoutePlanner()
        result = planner.plan("What is Rule 14A.35?")
        
        assert isinstance(result.validation_warnings, list)


class TestHeuristicRouteValidator:
    
    def test_detects_rule_number_conflict(self):
        validator = HeuristicRouteValidator()
        decision = RouteDecision(
            query_type="multi_hop",
            intent="comparison",
            requires_decomposition=True,
            retrieval_strategy="targeted_iterative"
        )
        query = "What is Rule 14A.35?"
        
        result = validator.validate(decision, query)
        
        assert result.is_valid is False or len(result.warnings) > 0
    
    def test_detects_comparison_keyword_conflict(self):
        validator = HeuristicRouteValidator()
        decision = RouteDecision(
            query_type="direct",
            intent="rule_lookup",
            requires_decomposition=False,
            retrieval_strategy="single_pass"
        )
        query = "Compare Rule 14A and Rule 14"
        
        result = validator.validate(decision, query)
        
        assert result.is_valid is False or len(result.warnings) > 0
    
    def test_detects_tool_keyword_conflict(self):
        validator = HeuristicRouteValidator()
        decision = RouteDecision(
            query_type="direct",
            intent="rule_lookup",
            requires_decomposition=False,
            retrieval_strategy="single_pass",
            tool_decision=ToolDecision(requires_tool=False)
        )
        query = "Calculate the size test ratio"
        
        result = validator.validate(decision, query)
        
        assert result.is_valid is False or len(result.warnings) > 0


class TestTaskDecomposer:
    
    def test_decomposes_comparison_query(self):
        decomposer = TaskDecomposer()
        route = RouteDecision(
            query_type="multi_hop",
            intent="comparison",
            requires_decomposition=True,
            retrieval_strategy="targeted_iterative"
        )
        query = "Compare disclosure requirements for connected and notifiable transactions"
        
        result = decomposer.decompose(query, route)
        
        assert isinstance(result, DecompositionPlan)
        assert len(result.subtasks) >= 2
        assert all(isinstance(task, SubTask) for task in result.subtasks)
    
    def test_subtasks_have_dependencies(self):
        decomposer = TaskDecomposer()
        route = RouteDecision(
            query_type="multi_hop",
            intent="comparison",
            requires_decomposition=True,
            retrieval_strategy="targeted_iterative"
        )
        query = "Compare disclosure requirements for connected and notifiable transactions"
        
        result = decomposer.decompose(query, route)
        
        for task in result.subtasks:
            assert task.id is not None
            assert task.goal is not None
            assert task.query is not None
    
    def test_fallback_on_llm_failure(self):
        decomposer = TaskDecomposer(llm_client=None)
        route = RouteDecision(
            query_type="multi_hop",
            intent="comparison",
            requires_decomposition=True,
            retrieval_strategy="targeted_iterative"
        )
        query = "Compare A and B"
        
        result = decomposer.decompose(query, route)
        
        assert isinstance(result, DecompositionPlan)
        assert result.fallback_used is True


class TestDecompositionValidator:
    
    def test_detects_incomplete_subtasks(self):
        validator = DecompositionValidator()
        plan = DecompositionPlan(
            subtasks=[
                SubTask(id="t1", type="retrieval", goal="", query="What is Rule 14A?", depends_on=[])
            ]
        )
        
        result = validator.validate(plan)
        
        assert len(result.warnings) > 0 or len(result.errors) > 0
    
    def test_detects_dependency_cycles(self):
        validator = DecompositionValidator()
        plan = DecompositionPlan(
            subtasks=[
                SubTask(id="t1", type="retrieval", goal="Goal 1", query="Query 1", depends_on=["t2"]),
                SubTask(id="t2", type="retrieval", goal="Goal 2", query="Query 2", depends_on=["t1"])
            ]
        )
        
        result = validator.validate(plan)
        
        assert result.has_cycles is True
    
    def test_validates_comparison_has_two_retrieval_tasks(self):
        validator = DecompositionValidator()
        plan = DecompositionPlan(
            subtasks=[
                SubTask(id="t1", type="retrieval", goal="Get A", query="A", depends_on=[])
            ]
        )
        route = RouteDecision(query_type="multi_hop", intent="comparison")
        
        result = validator.validate(plan, route)
        
        assert len(result.warnings) > 0
