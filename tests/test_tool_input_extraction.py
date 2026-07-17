"""Tests for tool input extraction (refactored: heuristic-first with LLM fallback)."""

import pytest
from app.agents.tool_input_extraction_node import (
    extract_tool_inputs,
    _heuristic_extract,
    _parse_llm_response,
    _get_tool_schemas_text,
)
from app.tools.size_test_input_extractor import SizeTestInputExtractor


class TestParseLLMResponse:
    def test_extracts_tool_inputs_from_valid_json(self):
        content = '''{
            "issuer_market_cap": 1000,
            "transaction_consideration": 250
        }'''

        result = _parse_llm_response(content)

        assert result is not None
        assert result == {
            "issuer_market_cap": 1000,
            "transaction_consideration": 250,
        }

    def test_empty_input_returns_none(self):
        result = _parse_llm_response("")
        assert result is None

    def test_extracts_from_code_fenced_json(self):
        content = '''```json
        {
            "rule_number": "14.52"
        }
        ```'''

        result = _parse_llm_response(content)

        assert result is not None
        assert result == {"rule_number": "14.52"}


class TestGetToolSchemasText:
    def test_includes_all_four_tools(self):
        text = _get_tool_schemas_text()

        assert "size_test_calculator" in text
        assert "transaction_classifier" in text
        assert "disclosure_checklist" in text
        assert "rule_lookup" in text

    def test_includes_required_parameters(self):
        text = _get_tool_schemas_text()

        assert "issuer_market_cap" in text
        assert "REQUIRED" in text
        assert "highest_ratio" in text
        assert "rule_number" in text


class TestHeuristicExtraction:
    def test_extracts_rule_number(self):
        inputs = _heuristic_extract(
            "What does Rule 14.52 say about major transactions?",
            "rule_lookup",
        )
        assert inputs.get("rule_number") == "14.52"

    def test_extracts_rule_with_chapter_letter(self):
        inputs = _heuristic_extract("Lookup Rule 14A.35", "rule_lookup")
        assert inputs.get("rule_number") == "14A.35"

    def test_no_rule_number_returns_empty(self):
        inputs = _heuristic_extract("What is a major transaction?", "rule_lookup")
        assert "rule_number" not in inputs

    def test_classifier_extracts_ratio(self):
        inputs = _heuristic_extract(
            "Classify a disposal with ratio 75% and connected",
            "transaction_classifier",
        )
        assert inputs.get("highest_ratio") == 75

    def test_checklist_extracts_classification(self):
        inputs = _heuristic_extract(
            "What disclosure is needed for a major transaction?",
            "disclosure_checklist",
        )
        assert inputs.get("classification") is not None


class TestExtractToolInputs:
    def test_heuristic_fallback_for_rule_lookup(self):
        inputs = extract_tool_inputs("What does Rule 14.52 require?", "rule_lookup")
        assert inputs.get("rule_number") == "14.52"


def test_size_test_extractor_prefers_the_number_after_each_field_label():
    result = SizeTestInputExtractor().extract(
        "market cap: 1000; total assets: 2000; net assets: 800; annual profit: 120; "
        "shares outstanding: 1000; consideration: 180; acquired assets: 360; "
        "acquired profit: 21.6; acquired net assets: 144; transaction type: disposal"
    )

    assert result["issuer_market_cap"] == 1000
    assert result["issuer_total_assets"] == 2000
    assert result["issuer_net_assets"] == 800
    assert result["issuer_annual_profit"] == 120
    assert result["issuer_shares_outstanding"] == 1000
    assert result["transaction_consideration"] == 180
    assert result["acquired_assets"] == 360
    assert result["acquired_profit"] == 21.6
    assert result["acquired_net_assets"] == 144
    assert result["transaction_type"] == "disposal"
