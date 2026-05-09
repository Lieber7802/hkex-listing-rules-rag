"""Integration tests for multi-turn conversation support."""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.models.conversation import ConversationTurn


@pytest.fixture(autouse=True)
def reset_session_store(tmp_path):
    """Reset the global session store for each test to use temp dir."""
    import app.api.chat_v2 as chat_v2_module
    from app.services.session_store import SessionStore

    # Replace with fresh store using temp dir
    chat_v2_module.session_store = SessionStore(
        storage_path=tmp_path, ttl_minutes=60, max_turns=50
    )
    yield
    chat_v2_module.session_store = None


class TestMultiTurnAPI:
    """Test multi-turn conversation via API endpoints."""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_first_query_returns_conversation_id(self, client):
        """POST without conversation_id → response includes new conversation_id."""
        # Mock orchestrator
        with patch("app.api.chat_v2.get_orchestrator") as mock_orch:
            orch = MagicMock()
            orch.is_ready.return_value = True
            orch.process_query.return_value = {
                "query_type": "direct",
                "answer": "关联交易是指...",
                "citations": [],
                "retrieved_chunks": [],
                "uncertainty_note": None,
                "route_decision": None,
                "decomposition_plan": None,
                "route_validation": None,
                "decomposition_validation": None,
                "coverage_assessment": None,
                "selected_evidence": None,
                "verification_result": None,
                "confidence_level": "high",
                "retrieval_rounds": [],
                "tool_calls": [],
                "tool_results": [],
                "conversation_id": None,
            }
            mock_orch.return_value = orch

            response = client.post("/v2/chat", json={"query": "什么是关联交易?"})

        assert response.status_code == 200
        data = response.json()
        assert "conversation_id" in data
        assert data["conversation_id"] is not None
        assert len(data["conversation_id"]) == 36  # UUID format
        assert data["turn_number"] == 1

    def test_follow_up_returns_same_conversation_id(self, client):
        """POST with conversation_id → same ID returned, turn_number increments."""
        with patch("app.api.chat_v2.get_orchestrator") as mock_orch:
            orch = MagicMock()
            orch.is_ready.return_value = True
            orch.process_query.return_value = {
                "query_type": "direct",
                "answer": "Answer",
                "citations": [],
                "retrieved_chunks": [],
                "uncertainty_note": None,
                "route_decision": None,
                "decomposition_plan": None,
                "route_validation": None,
                "decomposition_validation": None,
                "coverage_assessment": None,
                "selected_evidence": None,
                "verification_result": None,
                "confidence_level": "high",
                "retrieval_rounds": [],
                "tool_calls": [],
                "tool_results": [],
                "conversation_id": None,
            }
            mock_orch.return_value = orch

            # First turn
            r1 = client.post("/v2/chat", json={"query": "什么是关联交易?"})
            cid = r1.json()["conversation_id"]
            assert r1.json()["turn_number"] == 1

            # Second turn with same conversation_id
            r2 = client.post("/v2/chat", json={
                "query": "它有什么豁免?",
                "conversation_id": cid
            })

        assert r2.status_code == 200
        data2 = r2.json()
        assert data2["conversation_id"] == cid
        assert data2["turn_number"] == 2

    def test_invalid_conversation_id_creates_new_session(self, client):
        """POST with invalid conversation_id → graceful fallback to new session."""
        with patch("app.api.chat_v2.get_orchestrator") as mock_orch:
            orch = MagicMock()
            orch.is_ready.return_value = True
            orch.process_query.return_value = {
                "query_type": "direct",
                "answer": "Answer",
                "citations": [],
                "retrieved_chunks": [],
                "uncertainty_note": None,
                "route_decision": None,
                "decomposition_plan": None,
                "route_validation": None,
                "decomposition_validation": None,
                "coverage_assessment": None,
                "selected_evidence": None,
                "verification_result": None,
                "confidence_level": "high",
                "retrieval_rounds": [],
                "tool_calls": [],
                "tool_results": [],
                "conversation_id": None,
            }
            mock_orch.return_value = orch

            response = client.post("/v2/chat", json={
                "query": "test query",
                "conversation_id": "nonexistent-fake-id-12345"
            })

        assert response.status_code == 200
        data = response.json()
        # Should get a new valid conversation_id (not the fake one)
        assert data["conversation_id"] != "nonexistent-fake-id-12345"
        assert data["conversation_id"] is not None

    def test_no_conversation_id_backward_compatible(self, client):
        """Without conversation_id, behaves like before (no error)."""
        with patch("app.api.chat_v2.get_orchestrator") as mock_orch:
            orch = MagicMock()
            orch.is_ready.return_value = True
            orch.process_query.return_value = {
                "query_type": "direct",
                "answer": "Answer",
                "citations": [],
                "retrieved_chunks": [],
                "uncertainty_note": None,
                "route_decision": None,
                "decomposition_plan": None,
                "route_validation": None,
                "decomposition_validation": None,
                "coverage_assessment": None,
                "selected_evidence": None,
                "verification_result": None,
                "confidence_level": None,
                "retrieval_rounds": [],
                "tool_calls": [],
                "tool_results": [],
                "conversation_id": None,
            }
            mock_orch.return_value = orch

            response = client.post("/v2/chat", json={"query": "什么是Rule 14A?"})

        assert response.status_code == 200
        assert response.json()["answer"] == "Answer"


class TestQueryRewriteIntegration:
    """Test that query rewriting integrates correctly."""

    def test_rewriter_is_self_contained_skips_rewrite(self):
        """Self-contained query should not be rewritten."""
        from app.agents.contextual_query_rewriter import ContextualQueryRewriter

        rewriter = ContextualQueryRewriter()
        history = [
            ConversationTurn(role="user", content="什么是关联交易?"),
            ConversationTurn(role="assistant", content="关联交易是指..."),
        ]

        # Self-contained query: no rewrite
        result = rewriter.rewrite("Chapter 14的规则是什么?", history)
        assert result == "Chapter 14的规则是什么?"

    def test_rewriter_ambiguous_triggers_rewrite_path(self):
        """Ambiguous query with history should attempt rewrite."""
        from app.agents.contextual_query_rewriter import ContextualQueryRewriter

        rewriter = ContextualQueryRewriter()

        # Verify detection
        assert not rewriter._is_self_contained("它有哪些豁免?")

    def test_history_formatter_integration(self):
        """HistoryFormatter correctly formats turns for LLM."""
        from app.services.history_formatter import HistoryFormatter

        formatter = HistoryFormatter()
        turns = [
            ConversationTurn(role="user", content="什么是关联交易?"),
            ConversationTurn(role="assistant", content="关联交易是指上市公司与关联人士的交易"),
            ConversationTurn(role="user", content="它有什么豁免?"),
            ConversationTurn(role="assistant", content="豁免包括..."),
        ]

        messages, summary = formatter.format_for_reasoning(turns, max_turns=5)
        assert len(messages) == 4
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "什么是关联交易?"
        assert summary is None  # All fits in window


class TestReasoningAgentHistory:
    """Test ReasoningAgent with chat history injection."""

    def test_reason_without_history_unchanged(self):
        """Calling reason without history works exactly as before."""
        from app.agents.reasoning_agent import ReasoningAgent
        from app.schemas.query import PlannerOutput
        from app.retrieval.hybrid_retriever import RetrievalResult
        from app.schemas.document import Chunk

        agent = ReasoningAgent()
        planner_output = PlannerOutput(query_type="direct", sub_queries=[])

        chunk = Chunk(
            chunk_id="test-1",
            document_id="doc-1",
            text="Rule 14A.01 defines connected transactions.",
            rule_number="14A.01",
            section_title="Connected Transactions",
            source_path="test.md",
            chapter="14A",
        )
        result_obj = RetrievalResult(
            chunk_id="test-1", chunk=chunk, score=0.9, bm25_score=0.5, dense_score=0.9
        )

        # Without LLM, uses fallback
        output = agent.reason("What is Rule 14A?", planner_output, [result_obj])
        assert output.answer  # Should produce an answer
        assert "14A" in output.answer

    def test_reason_with_history_parameter_accepted(self):
        """Verify reason() accepts chat_history without error."""
        from app.agents.reasoning_agent import ReasoningAgent
        from app.schemas.query import PlannerOutput
        from app.retrieval.hybrid_retriever import RetrievalResult
        from app.schemas.document import Chunk

        agent = ReasoningAgent()
        planner_output = PlannerOutput(query_type="direct", sub_queries=[])

        chunk = Chunk(
            chunk_id="test-1",
            document_id="doc-1",
            text="Rule 14A.01 connected transactions",
            rule_number="14A.01",
            section_title="Connected Transactions",
            source_path="test.md",
            chapter="14A",
        )
        result_obj = RetrievalResult(
            chunk_id="test-1", chunk=chunk, score=0.9, bm25_score=0.5, dense_score=0.9
        )

        history = [
            {"role": "user", "content": "什么是关联交易?"},
            {"role": "assistant", "content": "关联交易是指..."},
        ]

        # Should not raise
        output = agent.reason(
            "它有什么豁免?",
            planner_output,
            [result_obj],
            chat_history=history,
        )
        assert output.answer
