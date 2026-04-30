"""Tests for Planner tool routing enhancement (Sprint 7).

Tests:
- PlannerOutput gains tool_name and tool_mode fields
- PlannerAgent._select_tool_name maps intent → tool name
- PlannerAgent._select_tool_mode maps intent → tool mode
- V2 workflow uses planner_output.tool_name instead of hardcoded "size_test_calculator"
"""

import pytest
from app.agents.planner_agent import PlannerAgent
from app.schemas.query import PlannerOutput


class TestPlannerOutputToolFields:

    def test_tool_name_field_exists(self):
        output = PlannerOutput(
            query_type="direct",
            tool_name="size_test_calculator",
            tool_mode="tool_only",
        )
        assert output.tool_name == "size_test_calculator"

    def test_tool_name_defaults_none(self):
        output = PlannerOutput(query_type="direct")
        assert output.tool_name is None

    def test_tool_mode_defaults_none(self):
        output = PlannerOutput(query_type="direct")
        assert output.tool_mode == "none"

    def test_tool_mode_values(self):
        for mode in ["none", "tool_only", "tool_plus_retrieval"]:
            output = PlannerOutput(query_type="direct", tool_mode=mode)
            assert output.tool_mode == mode


class TestSelectToolName:

    def test_calculation_maps_to_size_test(self):
        planner = PlannerAgent()
        assert planner._select_tool_name("calculation_required", "calculate size test") == "size_test_calculator"

    def test_rule_lookup_maps_to_rule_lookup(self):
        planner = PlannerAgent()
        assert planner._select_tool_name("rule_lookup", "what is rule 14.52") == "rule_lookup"

    def test_general_returns_none(self):
        planner = PlannerAgent()
        assert planner._select_tool_name("general", "some query") is None

    def test_eligibility_maps_to_transaction_classifier(self):
        planner = PlannerAgent()
        name = planner._select_tool_name("eligibility_check", "classify transaction")
        assert name == "transaction_classifier"


class TestSelectToolMode:

    def test_calculation_returns_tool_only(self):
        planner = PlannerAgent()
        assert planner._select_tool_mode("calculation_required") == "tool_only"

    def test_rule_lookup_returns_tool_plus_retrieval(self):
        planner = PlannerAgent()
        assert planner._select_tool_mode("rule_lookup") == "tool_plus_retrieval"

    def test_general_returns_none(self):
        planner = PlannerAgent()
        assert planner._select_tool_mode("general") == "none"


class TestPlannerOutputIntegration:

    def test_plan_calculation_query_sets_tool_fields(self):
        planner = PlannerAgent()
        output = planner.plan("Calculate the size test ratio for this transaction")
        assert output.requires_tool is True
        assert output.tool_name == "size_test_calculator"
        assert output.tool_mode == "tool_only"

    def test_plan_rule_query_sets_rule_lookup(self):
        planner = PlannerAgent()
        output = planner.plan("What is rule 14.52?")
        assert output.tool_name == "rule_lookup"
        assert output.tool_mode == "tool_plus_retrieval"

    def test_plan_general_query_no_tool(self):
        planner = PlannerAgent()
        output = planner.plan("Tell me about listing requirements")
        assert output.tool_name is None
        assert output.tool_mode == "none"
