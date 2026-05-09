import pytest
from fastapi.testclient import TestClient
from app.main import app


client = TestClient(app)


class TestV2APIEndpoints:

    def test_v2_health_endpoint_exists(self):
        """V2 health check should be accessible at /v2/health."""
        response = client.get("/v2/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "version" in data

    def test_v2_chat_endpoint_exists(self):
        """V2 chat should be accessible at /v2/chat and return a valid response."""
        response = client.post("/v2/chat", json={"query": "What is Rule 14A.35?"})
        # V2 orchestrator runs to completion even without index (graceful fallback)
        assert response.status_code == 200
        data = response.json()
        assert "answer" in data
        assert "route_decision" in data

    def test_v1_endpoints_still_work(self):
        """V1 root endpoints must remain functional."""
        response = client.get("/health")
        assert response.status_code == 200

    def test_v1_and_v2_are_independent(self):
        """V1 and V2 health endpoints return independently."""
        v1 = client.get("/health")
        v2 = client.get("/v2/health")
        assert v1.status_code == 200
        assert v2.status_code == 200

    def test_root_endpoint_unchanged(self):
        """Root / endpoint returns project info or frontend HTML."""
        response = client.get("/")
        assert response.status_code == 200
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            data = response.json()
            assert "name" in data or "note" in data
        else:
            assert len(response.text) > 0
