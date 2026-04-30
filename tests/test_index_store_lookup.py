"""Tests for IndexStore.get_chunks_by_rule_number (Sprint 1b)."""

import pytest
import numpy as np

from app.schemas.document import Chunk
from app.retrieval.index_store import IndexStore


class TestGetChunksByRuleNumber:
    """Tests for the get_chunks_by_rule_number method on IndexStore."""

    def _make_store(self, chunks):
        """Build an IndexStore with the given chunks (no embeddings needed)."""
        store = IndexStore()
        store.chunks = chunks
        return store

    def test_matching_rule_number_returns_chunks(self):
        """Chunks whose rule_number matches the query are returned."""
        chunks = [
            Chunk(chunk_id="1", document_id="d1", source_path="a.md", text="Rule 14.52 text", rule_number="14.52"),
            Chunk(chunk_id="2", document_id="d1", source_path="a.md", text="Rule 14.52 cont", rule_number="14.52"),
            Chunk(chunk_id="3", document_id="d1", source_path="a.md", text="Rule 14A.35 text", rule_number="14A.35"),
        ]
        store = self._make_store(chunks)

        results = store.get_chunks_by_rule_number("14.52")

        assert len(results) == 2
        assert all(c.rule_number == "14.52" for c in results)
        assert {c.chunk_id for c in results} == {"1", "2"}

    def test_non_matching_returns_empty(self):
        """A rule_number not present in any chunk returns an empty list."""
        chunks = [
            Chunk(chunk_id="1", document_id="d1", source_path="a.md", text="Rule 14.52", rule_number="14.52"),
        ]
        store = self._make_store(chunks)

        results = store.get_chunks_by_rule_number("99.99")

        assert results == []

    def test_none_rule_number_chunks_excluded(self):
        """Chunks with rule_number=None are never returned."""
        chunks = [
            Chunk(chunk_id="1", document_id="d1", source_path="a.md", text="No rule", rule_number=None),
            Chunk(chunk_id="2", document_id="d1", source_path="a.md", text="Rule 14.52", rule_number="14.52"),
        ]
        store = self._make_store(chunks)

        results = store.get_chunks_by_rule_number("14.52")

        assert len(results) == 1
        assert results[0].chunk_id == "2"

    def test_empty_chunks_list(self):
        """An IndexStore with no chunks returns an empty list for any query."""
        store = self._make_store([])

        results = store.get_chunks_by_rule_number("14.52")

        assert results == []

    def test_results_preserve_chunk_order(self):
        """Returned chunks are sorted by chunk_order."""
        chunks = [
            Chunk(chunk_id="3", document_id="d1", source_path="a.md", text="Part 3", rule_number="14.52", chunk_order=2),
            Chunk(chunk_id="1", document_id="d1", source_path="a.md", text="Part 1", rule_number="14.52", chunk_order=0),
            Chunk(chunk_id="2", document_id="d1", source_path="a.md", text="Part 2", rule_number="14.52", chunk_order=1),
        ]
        store = self._make_store(chunks)

        results = store.get_chunks_by_rule_number("14.52")

        assert [c.chunk_id for c in results] == ["1", "2", "3"]
