"""Tests for simplified V2 route paths (retry/fallback removed, planner-first)."""

import pytest
from app.agents.langgraph_workflow_v2 import (
    LangGraphOrchestratorV2,
    should_route,
    tool_mode_router,
)
from app.schemas.planning import RouteDecision, ToolDecision


class TestShouldRoute:
    def test_tool_query_routes_to_execute_tool(self):
        route = RouteDecision(
            query_type="direct",
            intent="calculation_required",
            tool_decision=ToolDecision(requires_tool=True, tool_name="size_test_calculator"),
        )
        state = {"route_decision": route.model_dump()}
        assert should_route(state) == "execute_tool"

    def test_non_tool_query_routes_to_retrieve(self):
        route = RouteDecision(
            query_type="direct",
            intent="rule_lookup",
            tool_decision=ToolDecision(requires_tool=False),
        )
        state = {"route_decision": route.model_dump()}
        assert should_route(state) == "retrieve"

    def test_no_route_decision_defaults_to_retrieve(self):
        assert should_route({"route_decision": None}) == "retrieve"


class TestToolModeRouter:
    def test_tool_only_routes_to_select(self):
        route = RouteDecision(
            query_type="direct",
            tool_decision=ToolDecision(requires_tool=True, tool_mode="tool_only"),
        )
        state = {"route_decision": route.model_dump()}
        assert tool_mode_router(state) == "select"

    def test_tool_plus_retrieval_routes_to_retrieve(self):
        route = RouteDecision(
            query_type="direct",
            tool_decision=ToolDecision(requires_tool=True, tool_mode="tool_plus_retrieval"),
        )
        state = {"route_decision": route.model_dump()}
        assert tool_mode_router(state) == "retrieve"

    def test_no_route_defaults_to_retrieve(self):
        assert tool_mode_router({"route_decision": None}) == "retrieve"


class TestOrchestratorIntegration:
    def test_simple_query_completes_via_heuristic_path(self):
        orch = LangGraphOrchestratorV2(use_llm_planner=False)
        result = orch.process_query("What is Rule 14A.35?", use_llm_planner=False)

        assert result["query_type"] == "direct"
        assert result["answer"] is not None

    def test_hybrid_query_still_works(self):
        orch = LangGraphOrchestratorV2(use_llm_planner=False)
        result = orch.process_query(
            "Calculate the size test ratio for this acquisition",
            use_llm_planner=False,
        )

        assert result["answer"] is not None
        assert result["route_decision"] is not None
