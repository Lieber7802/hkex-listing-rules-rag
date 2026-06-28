import pytest
from app.schemas.planning import RouteDecision, ToolDecision, DecompositionPlan, SubTask
from app.agents.planner_agent import PlannerAgent
from app.schemas.query import PlannerOutput


class TestPlannerAgentRouteDecision:
    def test_simple_query_is_direct(self):
        planner = PlannerAgent()
        result = planner.plan("What is Rule 14A.35?")

        assert isinstance(result, PlannerOutput)
        assert result.query_type == "direct"
        assert result.intent == "rule_lookup"

    def test_comparison_query_is_multi_hop(self):
        planner = PlannerAgent()
        result = planner.plan("Compare disclosure requirements for connected and notifiable transactions")

        assert isinstance(result, PlannerOutput)
        assert result.query_type == "multi_hop"
        assert result.intent == "comparison"

    def test_calculation_query_requires_tool(self):
        planner = PlannerAgent()
        result = planner.plan("Calculate the size test ratio for this transaction")

        assert isinstance(result, PlannerOutput)
        assert result.requires_tool is True
        assert result.tool_name == "size_test_calculator"

    def test_planner_output_converts_to_route_decision(self):
        planner = PlannerAgent()
        planner_output = planner.plan("What is Rule 14A.35?")

        tool_decision = ToolDecision(
            requires_tool=planner_output.requires_tool,
            tool_name=planner_output.tool_name,
            tool_mode=planner_output.tool_mode if planner_output.requires_tool else "none",
        )

        route = RouteDecision(
            query_type=planner_output.query_type,
            intent=planner_output.intent,
            retrieval_strategy=planner_output.retrieval_strategy,
            tool_decision=tool_decision,
            answer_format=planner_output.answer_format,
            route_reason=planner_output.reason,
            sub_queries=list(planner_output.sub_queries),
        )

        assert isinstance(route, RouteDecision)
        assert route.query_type == planner_output.query_type
        assert route.intent == planner_output.intent

    def test_route_decision_to_planner_output(self):
        route = RouteDecision(
            query_type="multi_hop",
            intent="comparison",
            retrieval_strategy="multi_query",
            sub_queries=["Query A?", "Query B?"],
        )

        po = route.to_planner_output()

        assert po.query_type == "multi_hop"
        assert po.intent == "comparison"
        assert po.sub_queries == ["Query A?", "Query B?"]
        assert po.retrieval_strategy == "multi_query"


class TestSimplifiedSubTask:
    def test_subtask_minimal_fields(self):
        task = SubTask(id="t1", type="retrieval", query="What is Rule 14?")

        assert task.id == "t1"
        assert task.type == "retrieval"
        assert task.query == "What is Rule 14?"

    def test_decomposition_plan_simplified(self):
        plan = DecompositionPlan(
            subtasks=[
                SubTask(id="t1", type="retrieval", query="Query 1?"),
                SubTask(id="t2", type="retrieval", query="Query 2?"),
            ],
            decomposition_reason="test",
        )

        assert len(plan.subtasks) == 2
        assert plan.decomposition_reason == "test"


class TestToolInputExtraction:
    def test_rule_lookup_extraction(self):
        from app.agents.tool_input_extraction_node import extract_tool_inputs

        inputs = extract_tool_inputs("What does Rule 14A.35 say about connected transactions?", "rule_lookup")

        assert "rule_number" in inputs
        assert inputs["rule_number"] == "14A.35"

    def test_transaction_classifier_extraction(self):
        from app.agents.tool_input_extraction_node import extract_tool_inputs

        inputs = extract_tool_inputs(
            "Classify a connected acquisition with 75% ratio",
            "transaction_classifier",
        )

        assert "highest_ratio" in inputs
        assert inputs["highest_ratio"] == 75

    def test_size_test_extraction(self):
        from app.agents.tool_input_extraction_node import extract_tool_inputs

        inputs = extract_tool_inputs(
            "Calculate size test for an acquisition: assets 500 million, "
            "revenue 200 million, profit 50 million",
            "size_test_calculator",
        )

        assert isinstance(inputs, dict)
