"""Tests for tool_input_extraction_node (refactored heuristic-first + LLM fallback)."""

import pytest
import numpy as np

from app.schemas.document import Chunk
from app.retrieval.index_store import IndexStore
from app.agents.graph_state import AgentState
from app.schemas.planning import RouteDecision, ToolDecision
from app.agents.tool_input_extraction_node import (
    extract_tool_inputs,
    _heuristic_extract,
)


def _make_index_store():
    chunks = [Chunk(chunk_id="1", document_id="d1", source_path="a.md",
                     text="Rule 14.52 text", rule_number="14.52")]
    store = IndexStore()
    store.chunks = chunks
    embeddings = np.random.randn(1, 384).astype(np.float32)
    store.build_indexes(chunks, embeddings)
    return store


def _build_state(query, route_decision, **overrides):
    state: AgentState = {
        "query": query,
        "planner_output": None,
        "retrieved_chunks": [],
        "citations": [],
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
        "retrieval_rounds": [],
        "route_decision": route_decision.model_dump(),
        "decomposition_plan": None,
        "route_validation": None,
        "decomposition_validation": None,
        "use_llm_planner": False,
        "route_retry_count": 0,
        "tool_calls": [],
        "tool_results": [],
        "extraction_log": None,
    }
    state.update(overrides)
    return state


class TestHeuristicExtraction:
    def test_rule_lookup_extracts_number(self):
        result = _heuristic_extract("What is Rule 14.52?", "rule_lookup")
        assert result.get("rule_number") == "14.52"

    def test_rule_lookup_no_match(self):
        result = _heuristic_extract("what are the rules?", "rule_lookup")
        assert "rule_number" not in result

    def test_classifier_extracts_ratio(self):
        result = _heuristic_extract(
            "Classify with 75% ratio, acquisition, connected party",
            "transaction_classifier",
        )
        assert result.get("highest_ratio") == 75
        assert result.get("transaction_type") == "acquisition"
        assert result.get("is_connected") is True

    def test_checklist_extracts_fields(self):
        result = _heuristic_extract(
            "Disclosure checklist for major transaction with shareholder vote",
            "disclosure_checklist",
        )
        assert result.get("classification") == "major_transaction"
        assert result.get("shareholder_vote_required") is True

    def test_size_test_extracts_fields(self):
        result = _heuristic_extract(
            "Market cap 1000, assets 2000, consideration 250, acquisition",
            "size_test_calculator",
        )
        assert isinstance(result, dict)


class TestExtractToolInputs:
    def test_rule_lookup(self):
        result = extract_tool_inputs("What does Rule 14A.35 say?", "rule_lookup")
        assert result.get("rule_number") == "14A.35"

    def test_transaction_classifier(self):
        result = extract_tool_inputs(
            "Classify a disposal with 25% ratio",
            "transaction_classifier",
        )
        assert result.get("highest_ratio") == 25


class TestExtractionNode:
    def test_node_populates_empty_hint(self):
        from app.agents.langgraph_workflow_v2 import GraphNodes, tool_input_extraction_node

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
                tool_inputs_hint={},
            ),
        )

        state = _build_state(
            "Calculate size test: market cap 1000, consideration 250, acquisition",
            route_decision,
        )

        node_fn = tool_input_extraction_node(nodes)
        result = node_fn(state)

        assert result is not None
        assert "route_decision" in result
        assert "extraction_log" in result

    def test_node_skips_when_hint_already_populated(self):
        from app.agents.langgraph_workflow_v2 import GraphNodes, tool_input_extraction_node

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
                tool_inputs_hint={"issuer_market_cap": 1000, "transaction_type": "acquisition"},
            ),
        )

        state = _build_state("Calculate size test", route_decision)
        node_fn = tool_input_extraction_node(nodes)
        result = node_fn(state)

        assert result == {}

    def test_node_no_tool_required_returns_empty(self):
        from app.agents.langgraph_workflow_v2 import GraphNodes, tool_input_extraction_node

        store = _make_index_store()
        nodes = GraphNodes(index_store=store, use_llm_planner=False)

        route_decision = RouteDecision(
            query_type="direct",
            intent="general",
            requires_decomposition=False,
            tool_decision=ToolDecision(requires_tool=False, tool_mode="none"),
        )

        state = _build_state("What is a size test?", route_decision)
        node_fn = tool_input_extraction_node(nodes)
        result = node_fn(state)

        assert result == {}

    def test_node_rule_lookup_extraction(self):
        from app.agents.langgraph_workflow_v2 import GraphNodes, tool_input_extraction_node

        store = _make_index_store()
        nodes = GraphNodes(index_store=store, use_llm_planner=False)

        route_decision = RouteDecision(
            query_type="direct",
            intent="rule_lookup",
            requires_decomposition=False,
            tool_decision=ToolDecision(
                requires_tool=True,
                tool_name="rule_lookup",
                tool_mode="tool_plus_retrieval",
                tool_inputs_hint={},
            ),
        )

        state = _build_state("What does Rule 14A.35 say?", route_decision)
        node_fn = tool_input_extraction_node(nodes)
        result = node_fn(state)

        assert result is not None
        new_route = RouteDecision(**result["route_decision"])
        assert new_route.tool_decision.tool_inputs_hint.get("rule_number") == "14A.35"

    def test_node_classifier_extraction(self):
        from app.agents.langgraph_workflow_v2 import GraphNodes, tool_input_extraction_node

        store = _make_index_store()
        nodes = GraphNodes(index_store=store, use_llm_planner=False)

        route_decision = RouteDecision(
            query_type="direct",
            intent="calculation_required",
            requires_decomposition=False,
            tool_decision=ToolDecision(
                requires_tool=True,
                tool_name="transaction_classifier",
                tool_mode="tool_only",
                tool_inputs_hint={},
            ),
        )

        state = _build_state(
            "Classify transaction with 60% ratio, acquisition of connected party",
            route_decision,
        )

        node_fn = tool_input_extraction_node(nodes)
        result = node_fn(state)

        assert result is not None
        new_route = RouteDecision(**result["route_decision"])
        hint = new_route.tool_decision.tool_inputs_hint
        assert hint.get("highest_ratio") == 60.0
        assert hint.get("transaction_type") == "acquisition"
        assert hint.get("is_connected") is True

    def test_node_checklist_extraction(self):
        from app.agents.langgraph_workflow_v2 import GraphNodes, tool_input_extraction_node

        store = _make_index_store()
        nodes = GraphNodes(index_store=store, use_llm_planner=False)

        route_decision = RouteDecision(
            query_type="direct",
            intent="obligation_summary",
            requires_decomposition=False,
            tool_decision=ToolDecision(
                requires_tool=True,
                tool_name="disclosure_checklist",
                tool_mode="tool_only",
                tool_inputs_hint={},
            ),
        )

        state = _build_state(
            "What disclosures needed for major transaction with shareholder vote?",
            route_decision,
        )

        node_fn = tool_input_extraction_node(nodes)
        result = node_fn(state)

        assert result is not None
        new_route = RouteDecision(**result["route_decision"])
        hint = new_route.tool_decision.tool_inputs_hint
        assert hint.get("classification") == "major_transaction"
        assert hint.get("shareholder_vote_required") is True
