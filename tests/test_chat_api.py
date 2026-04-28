import pytest
from fastapi.testclient import TestClient
import numpy as np
from pathlib import Path
import tempfile

from app.main import app
from app.schemas.document import Chunk
from app.retrieval.index_store import IndexStore


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def mock_index_store():
    chunks = [
        Chunk(
            chunk_id="test-1",
            document_id="test-doc",
            source_path="test.md",
            text="Rule 14A.35 requires disclosure for connected transactions.",
            rule_number="14A.35",
            section_title="Disclosure Requirements"
        ),
        Chunk(
            chunk_id="test-2",
            document_id="test-doc",
            source_path="test.md",
            text="Connected transactions must be announced within 3 business days.",
            rule_number="14A.36",
            section_title="Announcement Requirements"
        ),
    ]
    
    embeddings = np.random.randn(2, 384).astype(np.float32)
    
    index_store = IndexStore()
    index_store.build_indexes(chunks, embeddings)
    
    return index_store


class TestHealthEndpoint:
    
    def test_health_returns_ok(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "version" in data


class TestChatEndpoint:
    
    def test_chat_without_index_returns_response(self, client):
        response = client.post("/chat", json={"query": "What is Rule 14A.35?"})
        assert response.status_code == 200
        data = response.json()
        assert "query_type" in data
        assert "answer" in data
    
    def test_chat_with_empty_query_returns_422(self, client):
        response = client.post("/chat", json={"query": ""})
        assert response.status_code == 422


class TestRootEndpoint:
    
    def test_root_returns_info(self, client):
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "version" in data
