import pytest
from app.agents.langgraph_workflow_v2 import (
    LangGraphOrchestratorV2,
    should_retry_route,
)
from app.schemas.planning import RouteValidationResult


class TestShouldRetryRoute:

    def test_continue_when_no_validation(self):
        state = {"route_validation": None, "route_retry_count": 0}
        assert should_retry_route(state) == "continue"

    def test_continue_when_valid(self):
        validation = RouteValidationResult(
            is_valid=True, should_retry=False, should_fallback=False
        )
        state = {"route_validation": validation.model_dump(), "route_retry_count": 0}
        assert should_retry_route(state) == "continue"

    def test_retry_when_should_retry(self):
        validation = RouteValidationResult(
            is_valid=False,
            should_retry=True,
            should_fallback=False,
            conflicts=["one conflict"],
        )
        state = {"route_validation": validation.model_dump(), "route_retry_count": 0}
        assert should_retry_route(state) == "retry"

    def test_fallback_when_should_fallback(self):
        validation = RouteValidationResult(
            is_valid=False,
            should_retry=False,
            should_fallback=True,
            conflicts=["c1", "c2", "c3"],
        )
        state = {"route_validation": validation.model_dump(), "route_retry_count": 0}
        assert should_retry_route(state) == "fallback"

    def test_fallback_when_retry_exhausted(self):
        """After 1 retry, should_retry becomes fallback."""
        validation = RouteValidationResult(
            is_valid=False,
            should_retry=True,
            should_fallback=False,
            conflicts=["one conflict"],
        )
        state = {"route_validation": validation.model_dump(), "route_retry_count": 1}
        assert should_retry_route(state) == "fallback"


class TestHeuristicFallbackIntegration:

    def test_conflicting_query_still_produces_valid_result(self):
        """A query that would cause route conflicts should still complete
        via the fallback path and produce a valid result."""
        orch = LangGraphOrchestratorV2(use_llm_planner=False)

        result = orch.process_query(
            "Calculate the size test ratio and compare Rule 14A versus Rule 14",
            use_llm_planner=False,
        )

        assert result["answer"] is not None
        assert result["route_decision"] is not None

    def test_simple_query_uses_continue_path(self):
        """A simple query should pass through route validation without retry/fallback."""
        orch = LangGraphOrchestratorV2(use_llm_planner=False)

        result = orch.process_query("What is Rule 14A.35?", use_llm_planner=False)

        assert result["query_type"] == "direct"
        assert result["answer"] is not None
