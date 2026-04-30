"""Tests for RuleLookupTool (Sprint 5).

Looks up rule text by rule_number using IndexStore.get_chunks_by_rule_number.
Normalizes input (strip "Rule " prefix, handle chapter letters).
"""

import pytest
from app.schemas.document import Chunk
from app.retrieval.index_store import IndexStore
from app.tools.rule_lookup import RuleLookupTool


def _make_store(chunks):
    """Build an IndexStore with chunks (no embeddings)."""
    store = IndexStore()
    store.chunks = chunks
    return store


@pytest.fixture
def chunks():
    return [
        Chunk(chunk_id="c1", document_id="d1", source_path="a.md", text="Content of rule 14.52 part 1", rule_number="14.52", chunk_order=0),
        Chunk(chunk_id="c2", document_id="d1", source_path="a.md", text="Content of rule 14.52 part 2", rule_number="14.52", chunk_order=1),
        Chunk(chunk_id="c3", document_id="d1", source_path="a.md", text="Content of rule 14A.35", rule_number="14A.35", chunk_order=0),
        Chunk(chunk_id="c4", document_id="d1", source_path="a.md", text="General section", rule_number=None, chunk_order=0),
    ]


@pytest.fixture
def tool(chunks):
    store = _make_store(chunks)
    return RuleLookupTool(index_store=store)


# ── Interface ────────────────────────────────────────────────────

class TestRuleLookupInterface:

    def test_name(self, tool):
        assert tool.name == "rule_lookup"

    def test_description_non_empty(self, tool):
        assert len(tool.description) > 10

    def test_input_schema_has_required(self, tool):
        assert "rule_number" in tool.input_schema["required"]


# ── Exact match ──────────────────────────────────────────────────

class TestExactMatch:

    def test_finds_matching_chunks(self, tool):
        r = tool.run({"rule_number": "14.52"})
        assert r["rule_found"] is True
        assert r["total_chunks"] == 2

    def test_returns_chunk_data(self, tool):
        r = tool.run({"rule_number": "14.52"})
        assert len(r["chunks"]) == 2
        assert r["chunks"][0]["chunk_id"] == "c1"
        assert r["chunks"][1]["chunk_id"] == "c2"

    def test_chunks_sorted_by_order(self, tool):
        r = tool.run({"rule_number": "14.52"})
        orders = [c["chunk_order"] for c in r["chunks"]]
        assert orders == sorted(orders)

    def test_chapter_letter_rule(self, tool):
        r = tool.run({"rule_number": "14A.35"})
        assert r["rule_found"] is True
        assert r["total_chunks"] == 1

    def test_retrieval_method_exact(self, tool):
        r = tool.run({"rule_number": "14.52"})
        assert r["retrieval_method"] == "exact_match"


# ── Normalization ────────────────────────────────────────────────

class TestInputNormalization:

    def test_strips_rule_prefix(self, tool):
        """'Rule 14.52' should be normalised to '14.52'."""
        r = tool.run({"rule_number": "Rule 14.52"})
        assert r["rule_found"] is True
        assert r["total_chunks"] == 2

    def test_strips_whitespace(self, tool):
        r = tool.run({"rule_number": "  14.52  "})
        assert r["rule_found"] is True


# ── Not found ────────────────────────────────────────────────────

class TestNotFound:

    def test_not_found(self, tool):
        r = tool.run({"rule_number": "99.99"})
        assert r["rule_found"] is False
        assert r["total_chunks"] == 0
        assert r["chunks"] == []
