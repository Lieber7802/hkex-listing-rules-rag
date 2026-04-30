import json
import re
from typing import Optional, Dict, Any, List
from app.schemas.planning import RouteDecision, ToolDecision
from app.agents.planner_agent import PlannerAgent
from app.core.config import settings
from app.core.logger import logger


class LLMRoutePlanner:
    def __init__(self, llm_client: Optional[Any] = None):
        self.llm_client = llm_client
        self.heuristic_planner = PlannerAgent()
        self.llm_provider = settings.llm_provider
        # Use deepseek-chat for structured JSON routing (Reasoner returns empty content for structured tasks)
        self.llm_model = "deepseek-chat" if settings.llm_model == "deepseek-reasoner" else settings.llm_model

    def plan(self, query: str) -> RouteDecision:
        llm_result = self._try_llm_plan(query)

        if llm_result is not None:
            llm_result.validation_warnings = []
            return llm_result

        fallback_result = self._heuristic_fallback(query)
        fallback_result.fallback_used = True
        logger.warning(f"LLM planning failed, using heuristic fallback for query: {query[:50]}")
        return fallback_result

    def _try_llm_plan(self, query: str) -> Optional[RouteDecision]:
        if self.llm_client is None:
            try:
                self.llm_client = self._get_llm_client()
            except Exception as e:
                logger.error(f"Failed to initialize LLM client: {e}")
                return None

        if self.llm_client is None:
            return None

        try:
            prompt = self._build_prompt(query)
            response = self.llm_client.chat.completions.create(
                model=self.llm_model,
                messages=[
                    {"role": "system", "content": self._get_system_prompt()},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=500
            )

            content = response.choices[0].message.content
            # DeepSeek Reasoner may put output in reasoning_content when content is empty
            if not content or not content.strip():
                reasoning = getattr(response.choices[0].message, 'reasoning_content', None)
                if reasoning:
                    content = reasoning
            return self._parse_llm_response(content)

        except Exception as e:
            logger.error(f"LLM planning error: {e}")
            return None

    def _get_llm_client(self):
        if self.llm_provider in ["openai", "deepseek"]:
            from openai import OpenAI
            import os
            api_key = settings.llm_api_key or os.environ.get("OPENAI_API_KEY") or os.environ.get("DEEPSEEK_API_KEY")
            if api_key:
                return OpenAI(api_key=api_key, base_url=settings.llm_base_url)
        return None

    def _get_tool_schemas_text(self) -> str:
        """Build text representation of available tool schemas for the system prompt."""
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

    def _get_system_prompt(self) -> str:
        tool_schemas = self._get_tool_schemas_text()
        return f"""You are a query routing planner for HKEX Listing Rules compliance Q&A system.

Your task is to analyze user queries and output a JSON routing decision.

Available tools and their input schemas:
{tool_schemas}

Output ONLY valid JSON with these fields:
{{
  "query_type": "direct" or "multi_hop",
  "intent": one of [rule_lookup, obligation_summary, comparison, eligibility_check, procedure_flow, calculation_required, conditional_judgment, general],
  "requires_decomposition": true or false,
  "retrieval_strategy": one of [single_pass, multi_query, targeted_iterative],
  "requires_tool": true or false,
  "tool_name": null or one of [size_test_calculator, rule_lookup, transaction_classifier, disclosure_checklist],
  "tool_mode": one of [none, tool_only, tool_plus_retrieval],
  "tool_inputs_hint": {{}} or dict of extracted parameter values from the query,
  "answer_format": one of [concise_with_citations, comparison_table, checklist_style],
  "route_reason": "brief explanation"
}}

Rules:
1. When requires_tool=true, you MUST extract all numeric values and parameters from the query into tool_inputs_hint matching the tool's input_schema.
2. If a value is not stated in the query, omit it from tool_inputs_hint (do NOT guess).
3. For size_test_calculator, extract financial figures in HK$ millions.
4. For rule_lookup, extract rule_number (e.g. "14.52", "14A.35").
5. For transaction_classifier, extract highest_ratio, transaction_type, is_connected.
6. Simple single-rule lookups should be "direct" with requires_decomposition=false.
7. Do NOT over-decompose simple questions."""

    def _build_prompt(self, query: str) -> str:
        return f"""Analyze this query and output a routing decision as JSON.

If the query contains numeric values or specific parameters needed for a tool, extract them into tool_inputs_hint.

Query: {query}

Output only valid JSON:"""

    def _parse_llm_response(self, content: str) -> Optional[RouteDecision]:
        try:
            if not content or not content.strip():
                return None

            json_str = content

            # Handle DeepSeek Reasoner <think>...</think> wrapper
            if "<think>" in json_str:
                # Extract content after </think>
                parts = json_str.split("</think>")
                if len(parts) > 1:
                    json_str = parts[-1].strip()
                else:
                    json_str = json_str.split("<think>")[0].strip()

            # Handle code fences
            if "```json" in json_str:
                json_str = json_str.split("```json")[1].split("```")[0]
            elif "```" in json_str:
                json_str = json_str.split("```")[1].split("```")[0]

            # Try to find JSON object in the content
            json_str = json_str.strip()
            if not json_str.startswith("{"):
                # Try to find first { ... } block
                start = json_str.find("{")
                end = json_str.rfind("}")
                if start != -1 and end != -1:
                    json_str = json_str[start:end + 1]

            data = json.loads(json_str.strip())

            # Extract tool_inputs_hint — parse from LLM output instead of hardcoding
            raw_hints = data.get("tool_inputs_hint", {})
            tool_inputs_hint = raw_hints if isinstance(raw_hints, dict) else {}

            tool_decision = ToolDecision(
                requires_tool=data.get("requires_tool", False),
                tool_name=data.get("tool_name"),
                tool_mode=data.get("tool_mode", "none"),
                tool_inputs_hint=tool_inputs_hint,
                tool_reason=data.get("route_reason")
            )

            return RouteDecision(
                query_type=data.get("query_type", "direct"),
                intent=data.get("intent", "general"),
                requires_decomposition=data.get("requires_decomposition", False),
                retrieval_strategy=data.get("retrieval_strategy", "single_pass"),
                tool_decision=tool_decision,
                answer_format=data.get("answer_format", "concise_with_citations"),
                route_reason=data.get("route_reason"),
                llm_confidence=0.8,
                validation_warnings=[],
                fallback_used=False
            )
        except Exception as e:
            logger.error(f"Failed to parse LLM response: {e}")
            return None

    def _extract_inputs_heuristic(self, query: str, tool_name: Optional[str]) -> Dict[str, Any]:
        """Regex-based extraction of tool parameters from query text."""
        inputs: Dict[str, Any] = {}

        if tool_name == "rule_lookup":
            match = re.search(r'[Rr]ule\s+([\d]+[A-Za-z]?\.[\d]+(?:\(\d+\))?)', query)
            if match:
                inputs["rule_number"] = match.group(1)

        return inputs

    def _heuristic_fallback(self, query: str) -> RouteDecision:
        planner_output = self.heuristic_planner.plan(query)

        # Extract tool inputs from query via heuristic regex
        tool_inputs_hint: Dict[str, Any] = {}
        if planner_output.requires_tool and planner_output.tool_name:
            tool_inputs_hint = self._extract_inputs_heuristic(query, planner_output.tool_name)

        tool_decision = ToolDecision(
            requires_tool=planner_output.requires_tool,
            tool_name=planner_output.tool_name,
            tool_mode=planner_output.tool_mode if planner_output.requires_tool else "none",
            tool_inputs_hint=tool_inputs_hint,
            tool_reason=None
        )

        return RouteDecision(
            query_type=planner_output.query_type,
            intent=planner_output.intent,
            requires_decomposition=planner_output.query_type == "multi_hop",
            retrieval_strategy=planner_output.retrieval_strategy,
            tool_decision=tool_decision,
            answer_format=planner_output.answer_format,
            route_reason=planner_output.reason,
            llm_confidence=0.5,
            validation_warnings=[],
            fallback_used=True
        )
