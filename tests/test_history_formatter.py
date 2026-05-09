"""Tests for HistoryFormatter service."""

import pytest
from unittest.mock import patch, MagicMock

from app.models.conversation import ConversationTurn
from app.services.history_formatter import HistoryFormatter


class TestHistoryFormatter:
    """Tests for HistoryFormatter."""

    @pytest.fixture
    def formatter(self):
        return HistoryFormatter()

    def _make_turns(self, count: int):
        """Helper to create count pairs of user/assistant turns."""
        turns = []
        for i in range(count):
            turns.append(ConversationTurn(role="user", content=f"Question {i+1}"))
            turns.append(ConversationTurn(role="assistant", content=f"Answer {i+1}"))
        return turns

    def test_format_as_messages_empty_history(self, formatter):
        result = formatter.format_as_messages([])
        assert result == []

    def test_format_as_messages_within_window(self, formatter):
        turns = self._make_turns(3)  # 3 pairs = 6 messages
        result = formatter.format_as_messages(turns, max_turns=5)
        assert len(result) == 6
        assert result[0] == {"role": "user", "content": "Question 1"}
        assert result[1] == {"role": "assistant", "content": "Answer 1"}

    def test_format_as_messages_exceeds_window(self, formatter):
        turns = self._make_turns(8)  # 8 pairs = 16 messages
        result = formatter.format_as_messages(turns, max_turns=3)
        # Only last 3 pairs = 6 messages
        assert len(result) == 6
        assert result[0] == {"role": "user", "content": "Question 6"}
        assert result[-1] == {"role": "assistant", "content": "Answer 8"}

    def test_format_for_reasoning_no_older(self, formatter):
        turns = self._make_turns(2)
        messages, summary = formatter.format_for_reasoning(turns, max_turns=5)
        assert len(messages) == 4
        assert summary is None

    def test_format_for_reasoning_with_older_generates_summary(self, formatter):
        turns = self._make_turns(8)
        with patch.object(formatter, 'generate_summary', return_value="Earlier discussion about connected transactions"):
            messages, summary = formatter.format_for_reasoning(turns, max_turns=3)
            assert len(messages) == 6  # last 3 pairs
            assert summary == "Earlier discussion about connected transactions"

    def test_generate_summary_no_llm_returns_fallback(self, formatter):
        """When LLM unavailable, generate_summary returns a simple concatenation."""
        turns = self._make_turns(3)
        # Without LLM client, should produce a fallback summary
        result = formatter.generate_summary(turns)
        assert result is not None
        assert len(result) > 0

    def test_format_as_messages_preserves_role_content_only(self, formatter):
        """Metadata and timestamp should not appear in formatted messages."""
        turns = [
            ConversationTurn(role="user", content="hi", metadata={"foo": "bar"}),
            ConversationTurn(role="assistant", content="hello", metadata={"x": 1}),
        ]
        result = formatter.format_as_messages(turns)
        for msg in result:
            assert set(msg.keys()) == {"role", "content"}

    def test_format_as_messages_single_user_turn(self, formatter):
        """Handle edge case: only a user turn, no assistant response yet."""
        turns = [ConversationTurn(role="user", content="hello")]
        result = formatter.format_as_messages(turns, max_turns=5)
        assert len(result) == 1
        assert result[0] == {"role": "user", "content": "hello"}
