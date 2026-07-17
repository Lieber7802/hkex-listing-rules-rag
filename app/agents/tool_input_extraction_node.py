"""Tool Input Extraction Node — LangGraph node that populates tool_inputs_hint.

Supports both LLM-based extraction (when LLM client is available) and
heuristic regex-based extraction (always available as fallback).
"""

from __future__ import annotations

import json
import re
from typing import Dict, Any, Optional
from datetime import datetime

from app.agents.graph_state import AgentState
from app.core.config import settings
from app.core.llm_client import get_llm_client
from app.core.logger import logger


def _parse_llm_response(content: str) -> Optional[Dict[str, Any]]:
    try:
        json_str = content
        if "<think>" in json_str:
            parts = json_str.split("</think>")
            json_str = parts[-1].strip() if len(parts) > 1 else json_str.split("<think>")[0].strip()
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0]
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0]
        json_str = json_str.strip()
        if not json_str.startswith("{"):
            start = json_str.find("{")
            end = json_str.rfind("}")
            if start != -1 and end != -1:
                json_str = json_str[start : end + 1]
        data = json.loads(json_str.strip())
        return data if isinstance(data, dict) else None
    except Exception as e:
        logger.warning(f"Failed to parse LLM tool extraction response: {e}")
        return None


def _llm_extract(query: str, tool_name: str) -> Dict[str, Any]:
    client = get_llm_client()
    if client is None:
        return {}

    schemas_text = _get_tool_schemas_text()
    system_prompt = f"""Extract tool parameters from the user query. Output ONLY valid JSON.
Available tools:
{schemas_text}
Return a JSON object with the parameter names and values. Only include parameters that are explicitly stated in the query. Do not guess."""

    try:
        response = client.chat.completions.create(
            model=settings.llm_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Extract parameters for tool '{tool_name}' from: {query}"},
            ],
            temperature=0.1,
            max_tokens=300,
        )
        content = response.choices[0].message.content
        if not content or not content.strip():
            reasoning = getattr(response.choices[0].message, "reasoning_content", None)
            if reasoning:
                content = reasoning
        data = _parse_llm_response(content)
        if data and isinstance(data, dict):
            cleaned = {k: v for k, v in data.items() if not k.startswith("_")}
            logger.info(f"LLM extracted {len(cleaned)} field(s) for {tool_name}")
            return cleaned
    except Exception as e:
        logger.warning(f"LLM tool extraction failed: {e}")
    return {}


def _get_tool_schemas_text() -> str:
    from app.tools.size_test_calculator import SizeTestCalculatorTool
    from app.tools.transaction_classifier import TransactionClassifierTool
    from app.tools.disclosure_checklist import DisclosureChecklistTool
    from app.tools.rule_lookup import RuleLookupTool

    tools = [
        SizeTestCalculatorTool(),
        TransactionClassifierTool(),
        DisclosureChecklistTool(),
        RuleLookupTool(),
    ]
    lines = []
    for tool in tools:
        schema = tool.input_schema
        required = schema.get("required", [])
        props = schema.get("properties", {})
        param_lines = []
        for pname, pdef in props.items():
            req_marker = " [REQUIRED]" if pname in required else ""
            param_lines.append(f"    - {pname} ({pdef.get('type', 'any')}): {pdef.get('description', '')}{req_marker}")
        lines.append(f"Tool: {tool.name}\n  Description: {tool.description}\n  Parameters:\n" + "\n".join(param_lines))
    return "\n\n".join(lines)


def _heuristic_extract(query: str, tool_name: str) -> Dict[str, Any]:
    inputs: Dict[str, Any] = {}

    if tool_name == "rule_lookup":
        match = re.search(r'[Rr]ule\s+([\d]+[A-Za-z]?\.[\d]+(?:\(\d+\))?)', query)
        if match:
            inputs["rule_number"] = match.group(1)
        else:
            from app.tools.query_parser import QueryParser
            rule_ref = QueryParser.extract_rule_reference(query)
            if rule_ref:
                inputs["rule_number"] = rule_ref

    elif tool_name == "size_test_calculator":
        from app.tools.size_test_input_extractor import SizeTestInputExtractor
        extractor = SizeTestInputExtractor()
        extracted = extractor.extract(query)
        for k, v in extracted.items():
            if not k.startswith("_"):
                inputs[k] = v

    elif tool_name == "transaction_classifier":
        from app.tools.query_parser import QueryParser
        percentages = QueryParser.extract_percentages(query)
        if percentages:
            inputs["highest_ratio"] = max(percentages)
        tx_type = QueryParser.extract_transaction_type(query)
        if tx_type:
            inputs["transaction_type"] = tx_type
        is_connected = any(w in query.lower() for w in ["connected", "related party", "associate"])
        inputs["is_connected"] = is_connected

    elif tool_name == "disclosure_checklist":
        from app.tools.query_parser import QueryParser
        tier = QueryParser.extract_classification_tier(query)
        if tier:
            inputs["classification"] = tier
        is_connected = any(w in query.lower() for w in ["connected", "related party"])
        inputs["is_connected"] = is_connected
        vote_required = any(w in query.lower() for w in ["shareholder vote", "shareholder approval", "shareholders' approval"])
        inputs["shareholder_vote_required"] = vote_required

    return inputs


def extract_tool_inputs(query: str, tool_name: str) -> Dict[str, Any]:
    heuristic_inputs = _heuristic_extract(query, tool_name)
    if _has_required_tool_inputs(tool_name, heuristic_inputs):
        logger.info(f"Heuristic extraction supplied required inputs for {tool_name}")
        return heuristic_inputs

    llm_inputs = _llm_extract(query, tool_name)
    if llm_inputs:
        return {**heuristic_inputs, **llm_inputs}
    logger.info(f"LLM extraction returned no results for {tool_name}, using heuristic")
    return heuristic_inputs


def _has_required_tool_inputs(tool_name: str, inputs: Dict[str, Any]) -> bool:
    required_by_tool = {
        "rule_lookup": {"rule_number"},
        "size_test_calculator": {"transaction_consideration", "transaction_type"},
        "transaction_classifier": {"highest_ratio", "transaction_type"},
        "disclosure_checklist": {"classification"},
    }
    return required_by_tool.get(tool_name, set()).issubset(inputs)


def tool_input_extraction_node(nodes):
    def node(state: AgentState) -> Dict[str, Any]:
        route_dict = state.get("route_decision")
        if not route_dict:
            return {}

        from app.schemas.planning import RouteDecision, ToolDecision
        route_decision = RouteDecision(**route_dict)
        tool_decision = route_decision.tool_decision

        if not tool_decision or not tool_decision.requires_tool:
            return {}

        tool_name = tool_decision.tool_name or ""
        existing_hints = dict(tool_decision.tool_inputs_hint) if tool_decision.tool_inputs_hint else {}
        query = state["query"]

        if existing_hints:
            logger.info(f"Tool input extraction: {tool_name} already has {len(existing_hints)} hint(s), skipping")
            return {}

        extracted = extract_tool_inputs(query, tool_name)
        merged_hints = {**existing_hints, **extracted}

        new_tool_decision = ToolDecision(
            requires_tool=tool_decision.requires_tool,
            tool_name=tool_decision.tool_name,
            tool_mode=tool_decision.tool_mode,
            tool_inputs_hint=merged_hints,
            tool_reason=tool_decision.tool_reason,
        )

        new_route = RouteDecision(
            query_type=route_decision.query_type,
            intent=route_decision.intent,
            requires_decomposition=route_decision.requires_decomposition,
            retrieval_strategy=route_decision.retrieval_strategy,
            tool_decision=new_tool_decision,
            answer_format=route_decision.answer_format,
            route_reason=route_decision.route_reason,
            llm_confidence=route_decision.llm_confidence,
            validation_warnings=route_decision.validation_warnings,
            fallback_used=route_decision.fallback_used,
            sub_queries=route_decision.sub_queries,
        )

        extraction_log = {
            "method": "llm" if get_llm_client() else "heuristic",
            "tool_name": tool_name,
            "extracted_fields": list(extracted.keys()),
            "extracted_at": datetime.now().isoformat(),
            "trigger_reason": "llm_hint_empty" if not existing_hints else "llm_hint_enhanced",
        }
        logger.info(f"Tool input extraction: {tool_name} extracted={list(extracted.keys())}")

        return {
            "route_decision": new_route.model_dump(),
            "extraction_log": extraction_log,
        }

    return node
