"""Tests for multi-turn conversation support in streaming endpoint."""

import json
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(autouse=True)
def reset_stream_session_store(tmp_path):
    """Reset the global session store for streaming tests."""
    import app.api.chat_v2_stream as stream_module
    from app.services.session_store import SessionStore

    stream_module._session_store = SessionStore(
        storage_path=tmp_path, ttl_minutes=60, max_turns=50
    )
    yield
    stream_module._session_store = None


class TestMultiTurnStreaming:
    """Test multi-turn conversation via streaming SSE endpoints."""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_stream_returns_conversation_id_in_done_event(self, client):
        """SSE done event should include conversation_id."""
        with patch("app.api.chat_v2_stream.get_streaming_orchestrator") as mock_orch:
            orch = MagicMock()
            orch.is_ready.return_value = True
            orch.stream_query.return_value = [
                {"event": "routing_complete", "data": {"query_type": "direct"}},
                {"event": "answer_chunk", "data": {"content": "Test answer"}},
                {"event": "done", "data": {"total_time_ms": 100, "tools_executed": 0}},
            ]
            mock_orch.return_value = orch

            response = client.post(
                "/v2/chat/stream",
                json={"query": "什么是关联交易?"},
            )

        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]

        # Parse SSE events
        events = _parse_sse(response.text)
        done_event = [e for e in events if e["event"] == "done"]
        assert len(done_event) == 1
        assert "conversation_id" in done_event[0]["data"]
        assert done_event[0]["data"]["conversation_id"] is not None

    def test_stream_with_conversation_id(self, client):
        """Streaming endpoint accepts conversation_id parameter."""
        with patch("app.api.chat_v2_stream.get_streaming_orchestrator") as mock_orch:
            orch = MagicMock()
            orch.is_ready.return_value = True
            orch.stream_query.return_value = [
                {"event": "routing_complete", "data": {"query_type": "direct"}},
                {"event": "answer_chunk", "data": {"content": "Answer 1"}},
                {"event": "done", "data": {"total_time_ms": 50, "tools_executed": 0}},
            ]
            mock_orch.return_value = orch

            # First request
            r1 = client.post("/v2/chat/stream", json={"query": "Q1"})
            events1 = _parse_sse(r1.text)
            done1 = [e for e in events1 if e["event"] == "done"][0]
            cid = done1["data"]["conversation_id"]

            # Second request with same conversation_id
            r2 = client.post("/v2/chat/stream", json={
                "query": "follow up",
                "conversation_id": cid,
            })

        events2 = _parse_sse(r2.text)
        done2 = [e for e in events2 if e["event"] == "done"][0]
        assert done2["data"]["conversation_id"] == cid
        assert done2["data"]["turn_number"] == 2

    def test_stream_get_with_conversation_id(self, client):
        """GET streaming endpoint accepts conversation_id query param."""
        with patch("app.api.chat_v2_stream.get_streaming_orchestrator") as mock_orch:
            orch = MagicMock()
            orch.is_ready.return_value = True
            orch.stream_query.return_value = [
                {"event": "done", "data": {"total_time_ms": 10, "tools_executed": 0}},
            ]
            mock_orch.return_value = orch

            response = client.get(
                "/v2/chat/stream",
                params={"query": "test", "conversation_id": "fake-id"},
            )

        assert response.status_code == 200

    def test_stream_saves_answer_to_session(self, client):
        """Answer from stream should be saved to session store."""
        import app.api.chat_v2_stream as stream_module

        with patch("app.api.chat_v2_stream.get_streaming_orchestrator") as mock_orch:
            orch = MagicMock()
            orch.is_ready.return_value = True
            orch.stream_query.return_value = [
                {"event": "answer_chunk", "data": {"content": "Part 1 "}},
                {"event": "answer_chunk", "data": {"content": "Part 2"}},
                {"event": "done", "data": {"total_time_ms": 100, "tools_executed": 0}},
            ]
            mock_orch.return_value = orch

            response = client.post("/v2/chat/stream", json={"query": "Q1"})

        events = _parse_sse(response.text)
        done = [e for e in events if e["event"] == "done"][0]
        cid = done["data"]["conversation_id"]

        # Check session store has the turns saved
        store = stream_module._session_store
        session = store.get_or_create(cid)
        assert len(session.turns) == 2  # user + assistant
        assert session.turns[0].role == "user"
        assert session.turns[0].content == "Q1"
        assert session.turns[1].role == "assistant"
        assert session.turns[1].content == "Part 1 Part 2"

    def test_stream_error_when_not_ready(self, client):
        """When service not ready, emit error event."""
        with patch("app.api.chat_v2_stream.get_streaming_orchestrator") as mock_orch:
            orch = MagicMock()
            orch.is_ready.return_value = False
            mock_orch.return_value = orch

            response = client.post("/v2/chat/stream", json={"query": "test"})

        assert response.status_code == 200
        events = _parse_sse(response.text)
        assert any(e["event"] == "error" for e in events)


def _parse_sse(text: str):
    """Parse SSE text into list of {event, data} dicts."""
    events = []
    current_event = None
    current_data = None

    for line in text.strip().split("\n"):
        if line.startswith("event: "):
            current_event = line[7:]
        elif line.startswith("data: "):
            current_data = json.loads(line[6:])
        elif line == "" and current_event is not None:
            events.append({"event": current_event, "data": current_data})
            current_event = None
            current_data = None

    # Handle last event if no trailing newline
    if current_event is not None and current_data is not None:
        events.append({"event": current_event, "data": current_data})

    return events
