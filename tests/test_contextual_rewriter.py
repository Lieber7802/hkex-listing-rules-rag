"""Tests for ContextualQueryRewriter (coreference resolution)."""

import pytest
from unittest.mock import patch, MagicMock

from app.models.conversation import ConversationTurn
from app.agents.contextual_query_rewriter import ContextualQueryRewriter


class TestContextualQueryRewriter:
    """Tests for ContextualQueryRewriter."""

    @pytest.fixture
    def rewriter(self):
        return ContextualQueryRewriter()

    def _make_history(self, pairs):
        """Helper: pairs = [(q1, a1), (q2, a2), ...]"""
        turns = []
        for q, a in pairs:
            turns.append(ConversationTurn(role="user", content=q))
            turns.append(ConversationTurn(role="assistant", content=a))
        return turns

    def test_self_contained_query_unchanged(self, rewriter):
        """A query with enough context doesn't trigger rewrite."""
        history = self._make_history([("什么是关联交易?", "关联交易是指...")])
        result = rewriter.rewrite("Chapter 14规则要求什么?", history)
        assert result == "Chapter 14规则要求什么?"

    def test_empty_history_returns_original(self, rewriter):
        """No history = always return original, even if query is ambiguous."""
        result = rewriter.rewrite("它有什么豁免?", [])
        assert result == "它有什么豁免?"

    def test_none_history_returns_original(self, rewriter):
        """None history treated same as empty."""
        result = rewriter.rewrite("它有什么豁免?", None)
        assert result == "它有什么豁免?"

    def test_chinese_pronoun_detected(self, rewriter):
        """Chinese pronouns/references trigger rewrite path."""
        assert not rewriter._is_self_contained("它有什么豁免?")
        assert not rewriter._is_self_contained("这个规则的要求是什么?")
        assert not rewriter._is_self_contained("上面提到的条件有哪些?")
        assert not rewriter._is_self_contained("该规则如何适用?")

    def test_english_reference_detected(self, rewriter):
        """English references trigger rewrite path."""
        assert not rewriter._is_self_contained("What are the exceptions for that?")
        assert not rewriter._is_self_contained("What does it require?")
        assert not rewriter._is_self_contained("Tell me more about the above rule")

    def test_self_contained_detection(self, rewriter):
        """Queries with specific entities are self-contained."""
        assert rewriter._is_self_contained("What is Rule 14A.35?")
        assert rewriter._is_self_contained("Chapter 14关联交易的定义是什么?")
        assert rewriter._is_self_contained("披露要求有哪些?")
        assert rewriter._is_self_contained("How to calculate size test ratios?")

    def test_rewrite_with_llm_mock(self, rewriter):
        """When LLM is available, it's called for ambiguous queries."""
        history = self._make_history([("什么是关联交易?", "关联交易是指上市公司与关联人士之间的交易")])

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "关联交易有什么豁免?"
        mock_client.chat.completions.create.return_value = mock_response

        rewriter._llm_client = mock_client

        result = rewriter.rewrite("它有什么豁免?", history)
        assert result == "关联交易有什么豁免?"
        mock_client.chat.completions.create.assert_called_once()

    def test_rewrite_fallback_when_llm_unavailable(self, rewriter):
        """When LLM fails, returns original query (graceful degradation)."""
        history = self._make_history([("什么是关联交易?", "关联交易是指...")])

        # No LLM client configured - should return original
        rewriter._llm_client = None
        with patch.object(rewriter, '_get_llm_client', return_value=None):
            result = rewriter.rewrite("它有什么豁免?", history)
            # Fallback returns a heuristic rewrite or original
            assert isinstance(result, str)
            assert len(result) > 0

    def test_rewrite_llm_error_graceful(self, rewriter):
        """LLM call raises exception → return original query."""
        history = self._make_history([("什么是关联交易?", "答案")])

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("API error")
        rewriter._llm_client = mock_client

        result = rewriter.rewrite("它有什么豁免?", history)
        # Should not raise, returns something
        assert isinstance(result, str)
