"""Tests for tool executor node and graph wiring (Sprint 6).

Tests:
- tool_executor_node: finds tool, executes, returns ToolCall+ToolResult in state
- tool_executor_node: tool not found → error result
- tool_executor_node: validation fails → error with message
- tool_mode_router: tool_only → "select", tool_plus_retrieval → "retrieve"
- should_route: 3-way routing (decompose / execute_tool / retrieve)
"""

import pytest
import numpy as np

from app.schemas.document import Chunk
from app.retrieval.index_store import IndexStore
from app.agents.graph_state import AgentState
from app.schemas.planning import RouteDecision, ToolDecision


def _make_index_store():
    """Build an IndexStore with a few chunks and fake embeddings."""
    chunks = [
        Chunk(chunk_id="1", document_id="d1", source_path="a.md",
              text="Rule 14.52 text", rule_number="14.52"),
    ]
    store = IndexStore()
    store.chunks = chunks
    embeddings = np.random.randn(1, 384).astype(np.float32)
    store.build_indexes(chunks, embeddings)
    return store


class TestToolExecutorNode:

    def test_tool_found_success(self):
        """When tool exists and inputs valid, tool_calls and tool_results populated."""
        from app.agents.langgraph_workflow_v2 import GraphNodes, tool_executor_node

        store = _make_index_store()
        nodes = GraphNodes(index_store=store, use_llm_planner=False)

        route_decision = RouteDecision(
            query_type="direct",
            intent="calculation_required",
            requires_decomposition=False,
            tool_decision=ToolDecision(
                requires_tool=True,
                tool_name="size_test_calculator",
                tool_mode="tool_only",
                tool_inputs_hint={
                    "issuer_market_cap": 1000,
                    "issuer_total_assets": 2000,
                    "issuer_net_assets": 500,
                    "issuer_annual_profit": 100,
                    "issuer_shares_outstanding": 10000,
                    "transaction_consideration": 250,
                    "acquired_assets": 600,
                    "acquired_profit": 60,
                    "acquired_net_assets": 150,
                    "consideration_shares": 0,
                    "transaction_type": "acquisition",
                },
            ),
        )

        state: AgentState = {
            "query": "Calculate size test",
            "route_decision": route_decision.model_dump(),
            "tool_calls": [],
            "tool_results": [],
            "retrieved_chunks": [],
            "citations": [],
            "retrieval_rounds": [],
            "planner_output": None,
            "answer": None,
            "uncertainty_note": None,
            "query_type": None,
            "error": None,
            "needs_second_retrieval": False,
            "iteration_count": 0,
            "coverage_assessment": None,
            "selected_evidence": None,
            "verification_result": None,
            "confidence_level": None,
            "decomposition_plan": None,
            "route_validation": None,
            "decomposition_validation": None,
            "use_llm_planner": False,
            "route_retry_count": 0,
        }

        node_fn = tool_executor_node(nodes)
        result = node_fn(state)

        assert len(result["tool_calls"]) >= 1
        assert result["tool_calls"][0]["tool_name"] == "size_test_calculator"
        assert len(result["tool_results"]) >= 1
        assert result["tool_results"][0]["success"] is True
        assert "ratios" in result["tool_results"][0]["output"]

    def test_tool_not_found_error(self):
        """When tool doesn't exist, tool_results has error."""
        from app.agents.langgraph_workflow_v2 import GraphNodes, tool_executor_node

        store = _make_index_store()
        nodes = GraphNodes(index_store=store, use_llm_planner=False)

        route_decision = RouteDecision(
            query_type="direct",
            intent="general",
            requires_decomposition=False,
            tool_decision=ToolDecision(
                requires_tool=True,
                tool_name="nonexistent_tool",
                tool_mode="tool_only",
            ),
        )

        state: AgentState = {
            "query": "test",
            "route_decision": route_decision.model_dump(),
            "tool_calls": [],
            "tool_results": [],
            "retrieved_chunks": [],
            "citations": [],
            "retrieval_rounds": [],
            "planner_output": None,
            "answer": None,
            "uncertainty_note": None,
            "query_type": None,
            "error": None,
            "needs_second_retrieval": False,
            "iteration_count": 0,
            "coverage_assessment": None,
            "selected_evidence": None,
            "verification_result": None,
            "confidence_level": None,
            "decomposition_plan": None,
            "route_validation": None,
            "decomposition_validation": None,
            "use_llm_planner": False,
            "route_retry_count": 0,
        }

        node_fn = tool_executor_node(nodes)
        result = node_fn(state)

        assert len(result["tool_results"]) == 1
        assert result["tool_results"][0]["success"] is False
        assert "not found" in result["tool_results"][0]["error"].lower()

    def test_validation_failure_error(self):
        """When tool inputs fail validation, tool_results has error."""
        from app.agents.langgraph_workflow_v2 import GraphNodes, tool_executor_node

        store = _make_index_store()
        nodes = GraphNodes(index_store=store, use_llm_planner=False)

        route_decision = RouteDecision(
            query_type="direct",
            intent="calculation_required",
            requires_decomposition=False,
            tool_decision=ToolDecision(
                requires_tool=True,
                tool_name="size_test_calculator",
                tool_mode="tool_only",
                tool_inputs_hint={},  # Missing required fields
            ),
        )

        state: AgentState = {
            "query": "test",
            "route_decision": route_decision.model_dump(),
            "tool_calls": [],
            "tool_results": [],
            "retrieved_chunks": [],
            "citations": [],
            "retrieval_rounds": [],
            "planner_output": None,
            "answer": None,
            "uncertainty_note": None,
            "query_type": None,
            "error": None,
            "needs_second_retrieval": False,
            "iteration_count": 0,
            "coverage_assessment": None,
            "selected_evidence": None,
            "verification_result": None,
            "confidence_level": None,
            "decomposition_plan": None,
            "route_validation": None,
            "decomposition_validation": None,
            "use_llm_planner": False,
            "route_retry_count": 0,
        }

        node_fn = tool_executor_node(nodes)
        result = node_fn(state)

        assert len(result["tool_results"]) == 1
        assert result["tool_results"][0]["success"] is False
        assert "validation" in result["tool_results"][0]["error"].lower() or "missing" in result["tool_results"][0]["error"].lower()


class TestToolModeRouter:

    def test_tool_only_routes_to_select(self):
        from app.agents.langgraph_workflow_v2 import tool_mode_router

        state: AgentState = {
            "query": "test",
            "route_decision": RouteDecision(
                query_type="direct", intent="calculation_required",
                requires_decomposition=False,
                tool_decision=ToolDecision(requires_tool=True, tool_mode="tool_only"),
            ).model_dump(),
            "tool_calls": [],
            "tool_results": [],
            "retrieved_chunks": [],
            "citations": [],
            "retrieval_rounds": [],
            "planner_output": None,
            "answer": None,
            "uncertainty_note": None,
            "query_type": None,
            "error": None,
            "needs_second_retrieval": False,
            "iteration_count": 0,
            "coverage_assessment": None,
            "selected_evidence": None,
            "verification_result": None,
            "confidence_level": None,
            "decomposition_plan": None,
            "route_validation": None,
            "decomposition_validation": None,
            "use_llm_planner": False,
            "route_retry_count": 0,
        }

        assert tool_mode_router(state) == "select"

    def test_tool_plus_retrieval_routes_to_retrieve(self):
        from app.agents.langgraph_workflow_v2 import tool_mode_router

        state: AgentState = {
            "query": "test",
            "route_decision": RouteDecision(
                query_type="direct", intent="calculation_required",
                requires_decomposition=False,
                tool_decision=ToolDecision(requires_tool=True, tool_mode="tool_plus_retrieval"),
            ).model_dump(),
            "tool_calls": [],
            "tool_results": [],
            "retrieved_chunks": [],
            "citations": [],
            "retrieval_rounds": [],
            "planner_output": None,
            "answer": None,
            "uncertainty_note": None,
            "query_type": None,
            "error": None,
            "needs_second_retrieval": False,
            "iteration_count": 0,
            "coverage_assessment": None,
            "selected_evidence": None,
            "verification_result": None,
            "confidence_level": None,
            "decomposition_plan": None,
            "route_validation": None,
            "decomposition_validation": None,
            "use_llm_planner": False,
            "route_retry_count": 0,
        }

        assert tool_mode_router(state) == "retrieve"


class TestShouldRoute:

    def test_decompose_when_requires_decomposition(self):
        from app.agents.langgraph_workflow_v2 import should_route

        state: AgentState = {
            "query": "test",
            "route_decision": RouteDecision(
                query_type="multi_hop", intent="general",
                requires_decomposition=True,
                tool_decision=ToolDecision(requires_tool=False),
            ).model_dump(),
            "tool_calls": [],
            "tool_results": [],
            "retrieved_chunks": [],
            "citations": [],
            "retrieval_rounds": [],
            "planner_output": None,
            "answer": None,
            "uncertainty_note": None,
            "query_type": None,
            "error": None,
            "needs_second_retrieval": False,
            "iteration_count": 0,
            "coverage_assessment": None,
            "selected_evidence": None,
            "verification_result": None,
            "confidence_level": None,
            "decomposition_plan": None,
            "route_validation": None,
            "decomposition_validation": None,
            "use_llm_planner": False,
            "route_retry_count": 0,
        }

        assert should_route(state) == "decompose"

    def test_execute_tool_when_requires_tool(self):
        from app.agents.langgraph_workflow_v2 import should_route

        state: AgentState = {
            "query": "test",
            "route_decision": RouteDecision(
                query_type="direct", intent="calculation_required",
                requires_decomposition=False,
                tool_decision=ToolDecision(requires_tool=True, tool_name="size_test_calculator", tool_mode="tool_only"),
            ).model_dump(),
            "tool_calls": [],
            "tool_results": [],
            "retrieved_chunks": [],
            "citations": [],
            "retrieval_rounds": [],
            "planner_output": None,
            "answer": None,
            "uncertainty_note": None,
            "query_type": None,
            "error": None,
            "needs_second_retrieval": False,
            "iteration_count": 0,
            "coverage_assessment": None,
            "selected_evidence": None,
            "verification_result": None,
            "confidence_level": None,
            "decomposition_plan": None,
            "route_validation": None,
            "decomposition_validation": None,
            "use_llm_planner": False,
            "route_retry_count": 0,
        }

        assert should_route(state) == "execute_tool"

    def test_retrieve_when_no_special_needs(self):
        from app.agents.langgraph_workflow_v2 import should_route

        state: AgentState = {
            "query": "test",
            "route_decision": RouteDecision(
                query_type="direct", intent="general",
                requires_decomposition=False,
                tool_decision=ToolDecision(requires_tool=False),
            ).model_dump(),
            "tool_calls": [],
            "tool_results": [],
            "retrieved_chunks": [],
            "citations": [],
            "retrieval_rounds": [],
            "planner_output": None,
            "answer": None,
            "uncertainty_note": None,
            "query_type": None,
            "error": None,
            "needs_second_retrieval": False,
            "iteration_count": 0,
            "coverage_assessment": None,
            "selected_evidence": None,
            "verification_result": None,
            "confidence_level": None,
            "decomposition_plan": None,
            "route_validation": None,
            "decomposition_validation": None,
            "use_llm_planner": False,
            "route_retry_count": 0,
        }

        assert should_route(state) == "retrieve"
