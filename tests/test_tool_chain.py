"""Tests for tool chain calling (Sprint 3)."""

import pytest
import numpy as np

from app.schemas.document import Chunk
from app.retrieval.index_store import IndexStore
from app.schemas.planning import RouteDecision, ToolDecision
from app.agents.graph_state import AgentState


def _make_index_store():
    chunks = [
        Chunk(chunk_id="1", document_id="d1", source_path="a.md",
              text="Rule 14.52 text", rule_number="14.52"),
    ]
    store = IndexStore()
    store.chunks = chunks
    embeddings = np.random.randn(1, 384).astype(np.float32)
    store.build_indexes(chunks, embeddings)
    return store


def _size_test_inputs():
    return {
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
    }


class TestToolChainDefinitions:

    def test_size_test_chains_to_classifier(self):
        from app.tools.tool_chain import TOOL_CHAINS
        assert "size_test_calculator" in TOOL_CHAINS
        targets = [c["target"] for c in TOOL_CHAINS["size_test_calculator"]]
        assert "transaction_classifier" in targets

    def test_classifier_chains_to_checklist(self):
        from app.tools.tool_chain import TOOL_CHAINS
        assert "transaction_classifier" in TOOL_CHAINS
        targets = [c["target"] for c in TOOL_CHAINS["transaction_classifier"]]
        assert "disclosure_checklist" in targets

    def test_rule_lookup_has_no_chain(self):
        from app.tools.tool_chain import TOOL_CHAINS
        assert "rule_lookup" not in TOOL_CHAINS


class TestResolveChainInputs:

    def test_size_test_to_classifier(self):
        from app.tools.tool_chain import resolve_chain_inputs
        source_output = {"highest_ratio": 30.0, "ratios": {}}
        inputs = resolve_chain_inputs(
            "size_test_calculator", source_output, "transaction_classifier",
            user_context={"transaction_type": "acquisition"}
        )
        assert inputs is not None
        assert inputs["highest_ratio"] == 30.0
        assert "is_connected" in inputs

    def test_classifier_to_checklist(self):
        from app.tools.tool_chain import resolve_chain_inputs
        source_output = {"classification": "major_transaction", "shareholder_vote_required": True}
        inputs = resolve_chain_inputs(
            "transaction_classifier", source_output, "disclosure_checklist",
            user_context={"is_connected": False}
        )
        assert inputs is not None
        assert inputs["classification"] == "major_transaction"
        assert inputs["shareholder_vote_required"] is True

    def test_returns_none_when_condition_fails(self):
        from app.tools.tool_chain import resolve_chain_inputs
        source_output = {"error": "Zero denominator", "ratios": {}}
        inputs = resolve_chain_inputs(
            "size_test_calculator", source_output, "transaction_classifier",
            user_context={}
        )
        assert inputs is None

    def test_user_context_overrides_defaults(self):
        from app.tools.tool_chain import resolve_chain_inputs
        source_output = {"highest_ratio": 30.0}
        inputs = resolve_chain_inputs(
            "size_test_calculator", source_output, "transaction_classifier",
            user_context={"is_connected": True}
        )
        assert inputs is not None
        assert inputs["is_connected"] is True


class TestShouldChain:

    def test_true_for_successful_size_test(self):
        from app.tools.tool_chain import should_chain
        assert should_chain("size_test_calculator", {"highest_ratio": 30.0}) is True

    def test_false_for_failed_size_test(self):
        from app.tools.tool_chain import should_chain
        assert should_chain("size_test_calculator", {"error": "bad"}) is False

    def test_false_for_rule_lookup(self):
        from app.tools.tool_chain import should_chain
        assert should_chain("rule_lookup", {"rule_found": True}) is False


class TestToolExecutorChain:

    def _make_state(self, tool_inputs):
        return {
            "query": "Calculate size test and classify",
            "route_decision": RouteDecision(
                query_type="direct",
                intent="calculation_required",
                requires_decomposition=False,
                tool_decision=ToolDecision(
                    requires_tool=True,
                    tool_name="size_test_calculator",
                    tool_mode="tool_only",
                    tool_inputs_hint=tool_inputs,
                ),
            ).model_dump(),
            "tool_calls": [], "tool_results": [],
            "retrieved_chunks": [], "citations": [], "retrieval_rounds": [],
            "planner_output": None, "answer": None, "uncertainty_note": None,
            "query_type": None, "error": None, "needs_second_retrieval": False,
            "iteration_count": 0, "coverage_assessment": None,
            "selected_evidence": None, "verification_result": None,
            "confidence_level": None, "decomposition_plan": None,
            "route_validation": None, "decomposition_validation": None,
            "use_llm_planner": False, "route_retry_count": 0,
        }

    def test_full_chain_three_tools(self):
        """size_test → classifier → checklist all execute."""
        from app.agents.langgraph_workflow_v2 import GraphNodes, tool_executor_node

        store = _make_index_store()
        nodes = GraphNodes(index_store=store, use_llm_planner=False)

        state = self._make_state(_size_test_inputs())
        node_fn = tool_executor_node(nodes)
        result = node_fn(state)

        assert len(result["tool_calls"]) == 3
        assert result["tool_calls"][0]["tool_name"] == "size_test_calculator"
        assert result["tool_calls"][1]["tool_name"] == "transaction_classifier"
        assert result["tool_calls"][2]["tool_name"] == "disclosure_checklist"
        assert all(r["success"] for r in result["tool_results"])

    def test_chain_stops_on_primary_failure(self):
        """If primary tool fails validation, no chain executes."""
        from app.agents.langgraph_workflow_v2 import GraphNodes, tool_executor_node

        store = _make_index_store()
        nodes = GraphNodes(index_store=store, use_llm_planner=False)

        state = self._make_state({})  # empty inputs → validation fail
        node_fn = tool_executor_node(nodes)
        result = node_fn(state)

        assert len(result["tool_calls"]) == 1
        assert result["tool_results"][0]["success"] is False

    def test_single_tool_no_chain(self):
        """rule_lookup has no chain → only 1 tool executes."""
        from app.agents.langgraph_workflow_v2 import GraphNodes, tool_executor_node

        store = _make_index_store()
        nodes = GraphNodes(index_store=store, use_llm_planner=False)

        state = {
            "query": "Rule 14.52",
            "route_decision": RouteDecision(
                query_type="direct", intent="rule_lookup",
                requires_decomposition=False,
                tool_decision=ToolDecision(
                    requires_tool=True, tool_name="rule_lookup",
                    tool_mode="tool_only",
                    tool_inputs_hint={"rule_number": "14.52"},
                ),
            ).model_dump(),
            "tool_calls": [], "tool_results": [],
            "retrieved_chunks": [], "citations": [], "retrieval_rounds": [],
            "planner_output": None, "answer": None, "uncertainty_note": None,
            "query_type": None, "error": None, "needs_second_retrieval": False,
            "iteration_count": 0, "coverage_assessment": None,
            "selected_evidence": None, "verification_result": None,
            "confidence_level": None, "decomposition_plan": None,
            "route_validation": None, "decomposition_validation": None,
            "use_llm_planner": False, "route_retry_count": 0,
        }

        node_fn = tool_executor_node(nodes)
        result = node_fn(state)

        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["tool_name"] == "rule_lookup"
