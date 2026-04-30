import pytest
import numpy as np
from pathlib import Path
import tempfile
import json

from app.schemas.document import Chunk
from app.retrieval.bm25 import BM25Index
from app.retrieval.index_store import VectorIndex, IndexStore
from app.retrieval.hybrid_retriever import HybridRetriever, RetrievalResult
from app.retrieval.embedder import BaseEmbedder


class MockEmbedder(BaseEmbedder):
    """Deterministic mock embedder for tests — no Ollama dependency."""

    def __init__(self, dimension: int = 384):
        self.dimension = dimension

    def embed(self, texts):
        # Use hash-based deterministic vectors so similar text gets similar embeddings
        result = np.zeros((len(texts), self.dimension), dtype=np.float32)
        for i, text in enumerate(texts):
            rng = np.random.RandomState(hash(text) % (2**31))
            result[i] = rng.randn(self.dimension).astype(np.float32)
        return result

    def embed_single(self, text):
        return self.embed([text])[0]


class TestBM25Index:
    
    def test_fit_creates_index(self):
        chunks = [
            Chunk(chunk_id="1", document_id="doc1", source_path="test.md", text="This is a test document about HKEX rules."),
            Chunk(chunk_id="2", document_id="doc1", source_path="test.md", text="Connected transactions require disclosure."),
            Chunk(chunk_id="3", document_id="doc1", source_path="test.md", text="Size tests determine transaction classification."),
        ]
        
        index = BM25Index()
        index.fit(chunks)
        
        assert index.corpus_size == 3
        assert len(index.doc_ids) == 3
    
    def test_search_returns_results(self):
        chunks = [
            Chunk(chunk_id="1", document_id="doc1", source_path="test.md", text="This is a test document about HKEX rules."),
            Chunk(chunk_id="2", document_id="doc1", source_path="test.md", text="Connected transactions require disclosure."),
            Chunk(chunk_id="3", document_id="doc1", source_path="test.md", text="Size tests determine transaction classification."),
        ]
        
        index = BM25Index()
        index.fit(chunks)
        
        results = index.search("connected transactions", top_k=2)
        
        assert len(results) > 0
        assert results[0][0] in ["1", "2", "3"]
    
    def test_save_and_load(self):
        chunks = [
            Chunk(chunk_id="1", document_id="doc1", source_path="test.md", text="Test document."),
        ]
        
        index = BM25Index()
        index.fit(chunks)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            index.save(Path(tmpdir))
            
            loaded_index = BM25Index.load(Path(tmpdir))
            
            assert loaded_index.corpus_size == 1
            assert loaded_index.doc_ids == ["1"]


class TestVectorIndex:
    
    def test_build_creates_index(self):
        chunks = [
            Chunk(chunk_id="1", document_id="doc1", source_path="test.md", text="Test document one."),
            Chunk(chunk_id="2", document_id="doc1", source_path="test.md", text="Test document two."),
        ]
        
        embeddings = np.random.randn(2, 384).astype(np.float32)
        
        index = VectorIndex(dimension=384)
        index.build(chunks, embeddings)
        
        assert index.index is not None
        assert len(index.chunk_ids) == 2
    
    def test_search_returns_results(self):
        chunks = [
            Chunk(chunk_id="1", document_id="doc1", source_path="test.md", text="Test document one."),
            Chunk(chunk_id="2", document_id="doc1", source_path="test.md", text="Test document two."),
        ]
        
        embeddings = np.random.randn(2, 384).astype(np.float32)
        embeddings = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)
        
        index = VectorIndex(dimension=384)
        index.build(chunks, embeddings)
        
        query_embedding = embeddings[0]
        results = index.search(query_embedding, top_k=2)
        
        assert len(results) > 0
        assert results[0][0] == "1"


class TestHybridRetriever:

    def test_normalize_scores_handles_empty(self):
        chunks = [
            Chunk(chunk_id="1", document_id="doc1", source_path="test.md", text="Test."),
        ]

        embeddings = np.random.randn(1, 384).astype(np.float32)

        index_store = IndexStore()
        index_store.build_indexes(chunks, embeddings)

        retriever = HybridRetriever(index_store)

        scores = []
        normalized = retriever._normalize_scores(scores)

        assert normalized == {}

    def test_normalize_scores_scales_to_zero_one(self):
        chunks = [
            Chunk(chunk_id="1", document_id="doc1", source_path="test.md", text="Test."),
        ]

        embeddings = np.random.randn(1, 384).astype(np.float32)

        index_store = IndexStore()
        index_store.build_indexes(chunks, embeddings)

        retriever = HybridRetriever(index_store)

        scores = [("a", 0.5), ("b", 1.0), ("c", 0.0)]
        normalized = retriever._normalize_scores(scores)

        assert normalized["c"] == 0.0
        assert normalized["b"] == 1.0
        assert 0.0 <= normalized["a"] <= 1.0

    def test_rrf_score_computation(self):
        """RRF score = sum of 1/(k + rank) across retrieval lists."""
        chunks = [
            Chunk(chunk_id="1", document_id="doc1", source_path="test.md", text="Test."),
        ]
        embeddings = np.random.randn(1, 384).astype(np.float32)
        index_store = IndexStore()
        index_store.build_indexes(chunks, embeddings)

        retriever = HybridRetriever(index_store, rrf_k=60)

        # chunk ranked #1 in BM25, #2 in dense → RRF = 1/(60+1) + 1/(60+2)
        bm25_ranks = [("a", 3), ("b", 2), ("c", 1)]  # a=rank1, b=rank2, c=rank3
        dense_ranks = [("b", 5), ("a", 4), ("c", 3)]  # b=rank1, a=rank2, c=rank3

        fused = retriever._rrf_fuse(bm25_ranks, dense_ranks)

        # "a": rank1 in bm25 + rank2 in dense = 1/61 + 1/62
        # "b": rank2 in bm25 + rank1 in dense = 1/62 + 1/61
        # Both "a" and "b" should have the same RRF score
        assert abs(fused["a"][0] - fused["b"][0]) < 1e-9

        # "c": rank3 in both = 1/63 + 1/63
        assert fused["c"][0] < fused["a"][0]

    def test_rrf_chunk_in_one_list_only(self):
        """A chunk appearing in only one retrieval list still gets an RRF score."""
        chunks = [
            Chunk(chunk_id="1", document_id="doc1", source_path="test.md", text="Test."),
        ]
        embeddings = np.random.randn(1, 384).astype(np.float32)
        index_store = IndexStore()
        index_store.build_indexes(chunks, embeddings)

        retriever = HybridRetriever(index_store, rrf_k=60)

        bm25_ranks = [("a", 10)]  # only "a" from BM25
        dense_ranks = [("b", 5)]   # only "b" from dense

        fused = retriever._rrf_fuse(bm25_ranks, dense_ranks)

        assert "a" in fused
        assert "b" in fused
        # "a" has BM25 rank 1, no dense → RRF = 1/(60+1)
        expected_a = 1.0 / (60 + 1)
        assert abs(fused["a"][0] - expected_a) < 1e-9
        # "b" has dense rank 1, no BM25 → RRF = 1/(60+1)
        expected_b = 1.0 / (60 + 1)
        assert abs(fused["b"][0] - expected_b) < 1e-9

    def test_rrf_k_parameter_default(self):
        """Default rrf_k should be 60."""
        chunks = [
            Chunk(chunk_id="1", document_id="doc1", source_path="test.md", text="Test."),
        ]
        embeddings = np.random.randn(1, 384).astype(np.float32)
        index_store = IndexStore()
        index_store.build_indexes(chunks, embeddings)

        retriever = HybridRetriever(index_store)
        assert retriever.rrf_k == 60

    def test_retrieve_returns_results(self):
        chunks = [
            Chunk(chunk_id="1", document_id="doc1", source_path="test.md", text="HKEX listing rules for connected transactions."),
            Chunk(chunk_id="2", document_id="doc1", source_path="test.md", text="Disclosure requirements for notifiable transactions."),
            Chunk(chunk_id="3", document_id="doc1", source_path="test.md", text="Size test calculations and thresholds."),
        ]

        mock_embedder = MockEmbedder(dimension=384)
        embeddings = mock_embedder.embed([c.text for c in chunks])

        index_store = IndexStore()
        index_store.build_indexes(chunks, embeddings)

        retriever = HybridRetriever(index_store, embedder=mock_embedder)

        results = retriever.retrieve("connected transactions")

        assert len(results) > 0
        assert all(isinstance(r, RetrievalResult) for r in results)
        assert all(r.chunk is not None for r in results)