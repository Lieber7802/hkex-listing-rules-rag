"""Tests for streaming SSE endpoint (Sprint 4)."""

import pytest
import json
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from app.main import app
    return TestClient(app)


class TestStreamingEndpoint:

    def test_post_returns_event_stream_content_type(self, client):
        """POST /v2/chat/stream returns text/event-stream."""
        from app.api import chat_v2_stream

        mock_orch = MagicMock()
        mock_orch.is_ready.return_value = True
        mock_orch.stream_query.return_value = iter([
            {"event": "routing_complete", "data": {"query_type": "direct"}},
            {"event": "done", "data": {"total_time_ms": 100, "tools_executed": 0}},
        ])

        with patch.object(chat_v2_stream, 'get_streaming_orchestrator', return_value=mock_orch):
            response = client.post(
                "/v2/chat/stream",
                json={"query": "What is Rule 14.52?"}
            )

        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]

    def test_post_emits_sse_formatted_events(self, client):
        """Response body has SSE format: event: ...\\ndata: ...\\n\\n"""
        from app.api import chat_v2_stream

        mock_orch = MagicMock()
        mock_orch.is_ready.return_value = True
        mock_orch.stream_query.return_value = iter([
            {"event": "routing_complete", "data": {"query_type": "direct"}},
            {"event": "done", "data": {"total_time_ms": 50, "tools_executed": 0}},
        ])

        with patch.object(chat_v2_stream, 'get_streaming_orchestrator', return_value=mock_orch):
            response = client.post(
                "/v2/chat/stream",
                json={"query": "test"}
            )

        body = response.text
        assert "event: routing_complete\n" in body
        assert "event: done\n" in body
        assert "data: " in body

    def test_get_endpoint_works(self, client):
        """GET /v2/chat/stream?query=... also works."""
        from app.api import chat_v2_stream

        mock_orch = MagicMock()
        mock_orch.is_ready.return_value = True
        mock_orch.stream_query.return_value = iter([
            {"event": "done", "data": {"total_time_ms": 10, "tools_executed": 0}},
        ])

        with patch.object(chat_v2_stream, 'get_streaming_orchestrator', return_value=mock_orch):
            response = client.get("/v2/chat/stream?query=hello")

        assert response.status_code == 200

    def test_error_event_when_not_ready(self, client):
        """When service not ready, emit error event."""
        from app.api import chat_v2_stream

        mock_orch = MagicMock()
        mock_orch.is_ready.return_value = False

        with patch.object(chat_v2_stream, 'get_streaming_orchestrator', return_value=mock_orch):
            response = client.post(
                "/v2/chat/stream",
                json={"query": "test"}
            )

        assert response.status_code == 200  # SSE always 200
        assert "event: error" in response.text

    def test_empty_query_returns_400(self, client):
        """Empty query returns 400 error."""
        response = client.post("/v2/chat/stream", json={"query": ""})
        assert response.status_code == 400

    def test_done_event_has_timing_data(self, client):
        """Done event includes total_time_ms."""
        from app.api import chat_v2_stream

        mock_orch = MagicMock()
        mock_orch.is_ready.return_value = True
        mock_orch.stream_query.return_value = iter([
            {"event": "done", "data": {"total_time_ms": 1234, "tools_executed": 2}},
        ])

        with patch.object(chat_v2_stream, 'get_streaming_orchestrator', return_value=mock_orch):
            response = client.post("/v2/chat/stream", json={"query": "test"})

        # Parse the done event data
        for line in response.text.split("\n"):
            if line.startswith("data: ") and "total_time_ms" in line:
                data = json.loads(line[6:])
                assert data["total_time_ms"] == 1234
                assert data["tools_executed"] == 2

    def test_original_chat_endpoint_unchanged(self, client):
        """Original /v2/chat still works synchronously."""
        response = client.post("/v2/chat", json={"query": "test"})
        assert response.status_code in (200, 503)

    def test_tool_executed_events_in_response(self, client):
        """tool_executed events emitted per tool in chain."""
        from app.api import chat_v2_stream

        mock_orch = MagicMock()
        mock_orch.is_ready.return_value = True
        mock_orch.stream_query.return_value = iter([
            {"event": "routing_complete", "data": {"query_type": "direct"}},
            {"event": "tool_executed", "data": {"tool_name": "size_test_calculator", "success": True}},
            {"event": "tool_executed", "data": {"tool_name": "transaction_classifier", "success": True}},
            {"event": "done", "data": {"total_time_ms": 500, "tools_executed": 2}},
        ])

        with patch.object(chat_v2_stream, 'get_streaming_orchestrator', return_value=mock_orch):
            response = client.post("/v2/chat/stream", json={"query": "calculate size test"})

        body = response.text
        assert body.count("event: tool_executed") == 2
