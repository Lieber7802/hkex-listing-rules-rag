"""Tests for LLM route planner tool input extraction (Sprint 1).

Tests:
- _parse_llm_response extracts tool_inputs_hint from valid JSON
- _parse_llm_response handles missing tool_inputs_hint (defaults {})
- _parse_llm_response handles non-dict tool_inputs_hint (defaults {})
- _parse_llm_response handles code-fenced JSON
- _get_tool_schemas_text includes all 4 tool names + required params
- _extract_inputs_heuristic extracts rule numbers for rule_lookup
- _extract_inputs_heuristic extracts rule with chapter letter
- _extract_inputs_heuristic returns empty when no rule found
- Heuristic fallback populates tool_inputs_hint for rule queries
- Heuristic fallback uses planner tool_name (not hardcoded)
"""

import pytest
from app.agents.llm_route_planner import LLMRoutePlanner


class TestParseToolInputsHint:

    def test_extracts_tool_inputs_from_valid_json(self):
        planner = LLMRoutePlanner()
        content = '''{
            "query_type": "direct",
            "intent": "calculation_required",
            "requires_decomposition": false,
            "retrieval_strategy": "single_pass",
            "requires_tool": true,
            "tool_name": "size_test_calculator",
            "tool_mode": "tool_only",
            "tool_inputs_hint": {
                "issuer_market_cap": 1000,
                "transaction_consideration": 250
            },
            "answer_format": "concise_with_citations",
            "route_reason": "Calculation query"
        }'''

        result = planner._parse_llm_response(content)

        assert result is not None
        assert result.tool_decision.tool_inputs_hint == {
            "issuer_market_cap": 1000,
            "transaction_consideration": 250,
        }

    def test_missing_tool_inputs_hint_defaults_empty(self):
        planner = LLMRoutePlanner()
        content = '''{
            "query_type": "direct",
            "intent": "general",
            "requires_decomposition": false,
            "retrieval_strategy": "single_pass",
            "requires_tool": false,
            "tool_name": null,
            "tool_mode": "none",
            "answer_format": "concise_with_citations",
            "route_reason": "Simple lookup"
        }'''

        result = planner._parse_llm_response(content)

        assert result is not None
        assert result.tool_decision.tool_inputs_hint == {}

    def test_non_dict_tool_inputs_hint_defaults_empty(self):
        planner = LLMRoutePlanner()
        content = '''{
            "query_type": "direct",
            "intent": "calculation_required",
            "requires_decomposition": false,
            "retrieval_strategy": "single_pass",
            "requires_tool": true,
            "tool_name": "size_test_calculator",
            "tool_mode": "tool_only",
            "tool_inputs_hint": "not a dict",
            "answer_format": "concise_with_citations",
            "route_reason": "bad"
        }'''

        result = planner._parse_llm_response(content)

        assert result is not None
        assert result.tool_decision.tool_inputs_hint == {}

    def test_extracts_from_code_fenced_json(self):
        planner = LLMRoutePlanner()
        content = '''Here is the routing decision:
```json
{
    "query_type": "direct",
    "intent": "rule_lookup",
    "requires_decomposition": false,
    "retrieval_strategy": "single_pass",
    "requires_tool": true,
    "tool_name": "rule_lookup",
    "tool_mode": "tool_plus_retrieval",
    "tool_inputs_hint": {"rule_number": "14.52"},
    "answer_format": "concise_with_citations",
    "route_reason": "Rule lookup"
}
```'''

        result = planner._parse_llm_response(content)

        assert result is not None
        assert result.tool_decision.tool_inputs_hint == {"rule_number": "14.52"}


class TestGetToolSchemasText:

    def test_includes_all_four_tools(self):
        planner = LLMRoutePlanner()
        text = planner._get_tool_schemas_text()

        assert "size_test_calculator" in text
        assert "transaction_classifier" in text
        assert "disclosure_checklist" in text
        assert "rule_lookup" in text

    def test_includes_required_parameters(self):
        planner = LLMRoutePlanner()
        text = planner._get_tool_schemas_text()

        assert "issuer_market_cap" in text
        assert "REQUIRED" in text
        assert "highest_ratio" in text
        assert "rule_number" in text


class TestHeuristicInputExtraction:

    def test_extracts_rule_number(self):
        planner = LLMRoutePlanner()
        inputs = planner._extract_inputs_heuristic(
            "What does Rule 14.52 say about major transactions?",
            "rule_lookup"
        )
        assert inputs.get("rule_number") == "14.52"

    def test_extracts_rule_with_chapter_letter(self):
        planner = LLMRoutePlanner()
        inputs = planner._extract_inputs_heuristic(
            "Lookup Rule 14A.35",
            "rule_lookup"
        )
        assert inputs.get("rule_number") == "14A.35"

    def test_no_rule_number_returns_empty(self):
        planner = LLMRoutePlanner()
        inputs = planner._extract_inputs_heuristic(
            "What is a major transaction?",
            "rule_lookup"
        )
        assert "rule_number" not in inputs


class TestHeuristicFallbackIntegration:

    def test_fallback_populates_rule_number(self):
        """Heuristic fallback extracts rule_number for rule_lookup queries."""
        planner = LLMRoutePlanner()
        # Force heuristic path (no LLM client)
        result = planner._heuristic_fallback("What does Rule 14.52 require?")

        if result.tool_decision.tool_name == "rule_lookup":
            assert result.tool_decision.tool_inputs_hint.get("rule_number") == "14.52"

    def test_fallback_uses_planner_tool_name(self):
        """Heuristic fallback uses PlannerAgent's tool_name, not hardcoded."""
        planner = LLMRoutePlanner()
        result = planner._heuristic_fallback("What is rule 14A.35?")

        # Should use rule_lookup (from PlannerAgent._select_tool_name)
        assert result.tool_decision.tool_name == "rule_lookup"
