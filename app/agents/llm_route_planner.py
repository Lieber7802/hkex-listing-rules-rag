import json
from typing import Optional, Dict, Any
from app.schemas.planning import RouteDecision, ToolDecision
from app.agents.planner_agent import PlannerAgent
from app.core.config import settings
from app.core.logger import logger


class LLMRoutePlanner:
    def __init__(self, llm_client: Optional[Any] = None):
        self.llm_client = llm_client
        self.heuristic_planner = PlannerAgent()
        self.llm_provider = settings.llm_provider
        self.llm_model = settings.llm_model
    
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
    
    def _get_system_prompt(self) -> str:
        return """You are a query routing planner for HKEX Listing Rules compliance Q&A system.

Your task is to analyze user queries and output a JSON routing decision.

Output ONLY valid JSON with these fields:
{
  "query_type": "direct" or "multi_hop",
  "intent": one of [rule_lookup, obligation_summary, comparison, eligibility_check, procedure_flow, calculation_required, conditional_judgment, general],
  "requires_decomposition": true or false,
  "retrieval_strategy": one of [single_pass, multi_query, targeted_iterative],
  "requires_tool": true or false,
  "tool_name": null or one of [size_test_calculator, rule_lookup, transaction_classifier, disclosure_checklist],
  "tool_mode": one of [none, tool_only, tool_plus_retrieval],
  "answer_format": one of [concise_with_citations, comparison_table, checklist_style],
  "route_reason": "brief explanation"
}

Rules:
1. Simple single-rule lookups should be "direct" with requires_decomposition=false
2. Comparisons, multi-condition questions should be "multi_hop" with requires_decomposition=true
3. Questions with "calculate", "ratio", "percentage", "size test" should have requires_tool=true
4. Do NOT over-decompose simple questions"""

    def _build_prompt(self, query: str) -> str:
        return f"""Analyze this query and output a routing decision as JSON:

Query: {query}

Output only valid JSON:"""
    
    def _parse_llm_response(self, content: str) -> Optional[RouteDecision]:
        try:
            json_str = content
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                json_str = content.split("```")[1].split("```")[0]
            
            data = json.loads(json_str.strip())
            
            tool_decision = ToolDecision(
                requires_tool=data.get("requires_tool", False),
                tool_name=data.get("tool_name"),
                tool_mode=data.get("tool_mode", "none"),
                tool_inputs_hint={},
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
    
    def _heuristic_fallback(self, query: str) -> RouteDecision:
        planner_output = self.heuristic_planner.plan(query)
        
        tool_decision = ToolDecision(
            requires_tool=planner_output.requires_tool,
            tool_name="size_test_calculator" if planner_output.requires_tool else None,
            tool_mode="tool_plus_retrieval" if planner_output.requires_tool else "none",
            tool_inputs_hint={},
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
