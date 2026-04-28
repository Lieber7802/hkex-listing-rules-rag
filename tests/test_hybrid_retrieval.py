import pytest
import numpy as np
from pathlib import Path
import tempfile
import json

from app.schemas.document import Chunk
from app.retrieval.bm25 import BM25Index
from app.retrieval.index_store import VectorIndex, IndexStore
from app.retrieval.hybrid_retriever import HybridRetriever, RetrievalResult


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
    
    def test_retrieve_returns_results(self):
        chunks = [
            Chunk(chunk_id="1", document_id="doc1", source_path="test.md", text="HKEX listing rules for connected transactions."),
            Chunk(chunk_id="2", document_id="doc1", source_path="test.md", text="Disclosure requirements for notifiable transactions."),
            Chunk(chunk_id="3", document_id="doc1", source_path="test.md", text="Size test calculations and thresholds."),
        ]
        
        embeddings = np.random.randn(3, 384).astype(np.float32)
        
        index_store = IndexStore()
        index_store.build_indexes(chunks, embeddings)
        
        retriever = HybridRetriever(index_store)
        
        results = retriever.retrieve("connected transactions")
        
        assert len(results) > 0
        assert all(isinstance(r, RetrievalResult) for r in results)
        assert all(r.chunk is not None for r in results)