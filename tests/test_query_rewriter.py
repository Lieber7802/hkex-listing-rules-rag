import pytest
from app.agents.query_rewriter import QueryRewriter


class TestQueryRewriter:

    def test_rewrite_from_missing_subtasks(self):
        rewriter = QueryRewriter()
        missing = [
            "disclosure requirements for connected transactions",
            "obligations under Rule 14A.35",
        ]
        rewritten = rewriter.rewrite(
            original_query="Compare connected and notifiable transactions",
            missing_information=missing,
        )
        assert len(rewritten) == 2
        assert all(isinstance(q, str) for q in rewritten)
        # Each rewritten query should incorporate the missing subtask focus
        assert any("connected" in q.lower() for q in rewritten)
        assert any("14A.35" in q for q in rewritten)

    def test_rewrite_empty_missing_returns_original(self):
        rewriter = QueryRewriter()
        rewritten = rewriter.rewrite(
            original_query="What is Rule 14A.35?",
            missing_information=[],
        )
        assert len(rewritten) == 1
        assert rewritten[0] == "What is Rule 14A.35?"

    def test_rewrite_extracts_rule_numbers(self):
        rewriter = QueryRewriter()
        missing = ["something about Rule 14A.35 and Rule 14.33"]
        rewritten = rewriter.rewrite(
            original_query="Compare rules",
            missing_information=missing,
        )
        # Should preserve rule numbers in rewritten queries
        combined = " ".join(rewritten)
        assert "14A.35" in combined or "14.33" in combined

    def test_rewrite_deduplicates(self):
        rewriter = QueryRewriter()
        missing = [
            "disclosure requirements",
            "disclosure requirements",
        ]
        rewritten = rewriter.rewrite(
            original_query="test",
            missing_information=missing,
        )
        assert len(rewritten) == len(set(rewritten))

    def test_rewrite_caps_at_three_queries(self):
        rewriter = QueryRewriter()
        missing = [f"subtask {i}" for i in range(10)]
        rewritten = rewriter.rewrite(
            original_query="big query",
            missing_information=missing,
        )
        assert len(rewritten) <= 3
