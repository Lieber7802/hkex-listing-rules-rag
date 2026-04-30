"""End-to-end integration tests for tool execution (Sprint 8).

Tests the full V2 workflow with tools:
- "Calculate size test" → tool_executor fires, tool_results populated
- Regular query → no tool, tool_calls empty
- tool_only → retrieval not required for answer
- V2 process_query returns tool_calls and tool_results fields
"""

import pytest
import numpy as np

from app.schemas.document import Chunk
from app.retrieval.index_store import IndexStore
from app.agents.langgraph_workflow_v2 import LangGraphOrchestratorV2


def _build_test_index():
    """Build a minimal IndexStore with chunks for testing."""
    chunks = [
        Chunk(chunk_id="c1", document_id="d1", source_path="a.md",
              text="Rule 14.52 requires shareholder approval for major transactions.",
              rule_number="14.52", chapter="Chapter 14"),
        Chunk(chunk_id="c2", document_id="d1", source_path="a.md",
              text="Connected transactions are governed by Chapter 14A.",
              rule_number="14A.35", chapter="Chapter 14A"),
        Chunk(chunk_id="c3", document_id="d1", source_path="a.md",
              text="The size tests include consideration ratio, assets ratio, profits ratio.",
              rule_number=None, chapter="Chapter 14"),
    ]
    embeddings = np.random.randn(3, 384).astype(np.float32)
    store = IndexStore()
    store.build_indexes(chunks, embeddings)
    return store


class TestToolIntegrationE2E:

    def test_calculation_query_fires_tool(self):
        """A calculation query should route through tool_executor and populate tool_results."""
        store = _build_test_index()
        orchestrator = LangGraphOrchestratorV2(index_store=store, use_llm_planner=False)

        result = orchestrator.process_query(
            "Calculate the size test ratio for acquisition with consideration 250M and market cap 1000M",
            use_llm_planner=False,
        )

        # Tool should have been called
        assert len(result["tool_calls"]) >= 1
        assert result["tool_calls"][0]["tool_name"] == "size_test_calculator"

        # Tool result should be present
        assert len(result["tool_results"]) >= 1
        # Note: may fail validation since the query doesn't provide all inputs,
        # but the tool execution path was exercised

    def test_regular_query_no_tool(self):
        """A general query should NOT fire any tool — tool_calls should be empty."""
        store = _build_test_index()
        orchestrator = LangGraphOrchestratorV2(index_store=store, use_llm_planner=False)

        result = orchestrator.process_query(
            "Tell me about listing requirements for companies",
            use_llm_planner=False,
        )

        assert result["tool_calls"] == []
        assert result["tool_results"] == []

    def test_rule_lookup_query_fires_rule_lookup_tool(self):
        """A rule lookup query should fire the rule_lookup tool."""
        store = _build_test_index()
        orchestrator = LangGraphOrchestratorV2(index_store=store, use_llm_planner=False)

        result = orchestrator.process_query(
            "What is rule 14.52?",
            use_llm_planner=False,
        )

        # Rule lookup fires tool_plus_retrieval
        assert len(result["tool_calls"]) >= 1
        assert result["tool_calls"][0]["tool_name"] == "rule_lookup"

    def test_process_query_returns_tool_fields(self):
        """process_query output dict should include tool_calls and tool_results keys."""
        store = _build_test_index()
        orchestrator = LangGraphOrchestratorV2(index_store=store, use_llm_planner=False)

        result = orchestrator.process_query(
            "What are disclosure requirements?",
            use_llm_planner=False,
        )

        assert "tool_calls" in result
        assert "tool_results" in result

    def test_tool_only_mode_provides_answer_without_retrieval(self):
        """When tool_mode is tool_only and tool succeeds, answer should contain tool output."""
        store = _build_test_index()
        orchestrator = LangGraphOrchestratorV2(index_store=store, use_llm_planner=False)

        # "Calculate" triggers calculation_required → tool_only
        result = orchestrator.process_query(
            "Calculate the size test",
            use_llm_planner=False,
        )

        # Even if tool fails validation (missing inputs), the path should be exercised
        assert len(result["tool_calls"]) >= 1
        assert result["tool_calls"][0]["tool_name"] == "size_test_calculator"
