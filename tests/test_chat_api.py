import json

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
    
    embeddings = np.zeros((2, 384), dtype=np.float32)
    embeddings[:, 0] = 1.0
    
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
    
    def test_chat_without_index_returns_service_unavailable(self, client):
        response = client.post("/chat", json={"query": "What is Rule 14A.35?"})
        assert response.status_code == 503
        data = response.json()
        assert "build the index" in data["detail"].lower()

    def test_chat_with_injected_index_returns_agentic_response(
        self,
        client,
        mock_index_store,
        monkeypatch,
    ):
        from app.agents.agentic_workflow import AgenticRAGOrchestrator
        from app.api import chat as chat_api

        monkeypatch.setattr(
            chat_api,
            "orchestrator",
            AgenticRAGOrchestrator(
                index_store=mock_index_store,
                use_llm_planner=False,
            ),
        )

        response = client.post("/chat", json={"query": "What is Rule 14A.35?"})

        assert response.status_code == 200
        data = response.json()
        assert data["route_decision"]["intent"] == "rule_lookup"
        assert data["selected_evidence"] is not None
        assert data["citations"]
        assert data["retrieval_rounds"]

    def test_stream_with_injected_index_preserves_sse_contract(
        self,
        client,
        mock_index_store,
        monkeypatch,
    ):
        from app.agents.streaming_workflow import StreamingOrchestrator
        from app.api import chat_stream as chat_stream_api

        monkeypatch.setattr(
            chat_stream_api,
            "_streaming_orchestrator",
            StreamingOrchestrator(index_store=mock_index_store),
        )

        response = client.post(
            "/chat/stream",
            json={
                "query": "What is Rule 14A.35?",
                "use_llm_planner": False,
            },
        )

        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        events = []
        for block in response.text.strip().split("\n\n"):
            lines = block.splitlines()
            event_type = lines[0].removeprefix("event: ")
            payload = json.loads(lines[1].removeprefix("data: "))
            events.append((event_type, payload))

        event_names = [event_type for event_type, _ in events]
        assert event_names[0] == "routing_complete"
        assert event_names[-1] == "done"
        assert event_names.index("retrieval_complete") < event_names.index("evidence_selected")
        assert event_names.index("evidence_selected") < event_names.index("answer_chunk")

        payloads = dict(events)
        assert payloads["routing_complete"]["query_type"] == "direct"
        assert payloads["retrieval_complete"]["num_chunks"] > 0
        assert payloads["answer_chunk"]["content"]
        assert payloads["done"]["total_time_ms"] >= 0
        assert payloads["done"]["conversation_id"]
    
    def test_chat_with_empty_query_returns_422(self, client):
        response = client.post("/chat", json={"query": ""})
        assert response.status_code == 422


class TestRootEndpoint:

    def test_root_returns_info(self, client):
        response = client.get("/")
        assert response.status_code == 200
        # May return HTML (frontend built) or JSON (fallback)
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            data = response.json()
            assert "name" in data or "note" in data
        else:
            # Frontend HTML served
            assert len(response.text) > 0
