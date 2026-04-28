import json
from typing import Optional, Any
from app.schemas.planning import DecompositionPlan, SubTask, RouteDecision
from app.core.config import settings
from app.core.logger import logger


class TaskDecomposer:
    def __init__(self, llm_client: Optional[Any] = None):
        self.llm_client = llm_client
        self.llm_provider = settings.llm_provider
        self.llm_model = settings.llm_model
    
    def decompose(self, query: str, route: RouteDecision) -> DecompositionPlan:
        llm_result = self._try_llm_decompose(query, route)
        
        if llm_result is not None:
            llm_result.validation_warnings = []
            return llm_result
        
        fallback_result = self._heuristic_fallback(query, route)
        fallback_result.fallback_used = True
        logger.warning(f"LLM decomposition failed, using heuristic fallback for query: {query[:50]}")
        return fallback_result
    
    def _try_llm_decompose(self, query: str, route: RouteDecision) -> Optional[DecompositionPlan]:
        if self.llm_client is None:
            try:
                self.llm_client = self._get_llm_client()
            except Exception as e:
                logger.error(f"Failed to initialize LLM client: {e}")
                return None
        
        if self.llm_client is None:
            return None
        
        try:
            prompt = self._build_prompt(query, route)
            response = self.llm_client.chat.completions.create(
                model=self.llm_model,
                messages=[
                    {"role": "system", "content": self._get_system_prompt()},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=800
            )
            
            content = response.choices[0].message.content
            return self._parse_llm_response(content)
        
        except Exception as e:
            logger.error(f"LLM decomposition error: {e}")
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
        return """You are a task decomposition specialist for HKEX Listing Rules compliance Q&A system.

Your task is to decompose complex queries into structured, executable subtasks.

Output ONLY valid JSON with these fields:
{
  "subtasks": [
    {
      "id": "task_1",
      "type": "retrieval" or "tool" or "reasoning_prep",
      "goal": "clear goal description",
      "query": "specific query for this subtask",
      "depends_on": [],
      "priority": "high" or "medium" or "low"
    }
  ],
  "merge_strategy": "sequential" or "parallel" or "hierarchical",
  "coverage_targets": ["target1", "target2"],
  "decomposition_reason": "brief explanation"
}

Rules:
1. Each subtask must be complete and independently executable
2. Use "depends_on" to specify task dependencies
3. For comparisons, create at least 2 retrieval tasks + 1 merge task
4. For tool queries, create tool task + retrieval task for context
5. Subtask queries should be complete sentences, not fragments"""

    def _build_prompt(self, query: str, route: RouteDecision) -> str:
        return f"""Decompose this query into subtasks:

Query: {query}
Intent: {route.intent}
Query Type: {route.query_type}
Requires Tool: {route.tool_decision.requires_tool}

Output only valid JSON:"""
    
    def _parse_llm_response(self, content: str) -> Optional[DecompositionPlan]:
        try:
            json_str = content
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                json_str = content.split("```")[1].split("```")[0]
            
            data = json.loads(json_str.strip())
            
            subtasks = []
            for task_data in data.get("subtasks", []):
                subtasks.append(SubTask(
                    id=task_data.get("id", f"task_{len(subtasks)+1}"),
                    type=task_data.get("type", "retrieval"),
                    goal=task_data.get("goal", ""),
                    query=task_data.get("query", ""),
                    depends_on=task_data.get("depends_on", []),
                    priority=task_data.get("priority", "medium"),
                    expected_output=task_data.get("expected_output")
                ))
            
            return DecompositionPlan(
                subtasks=subtasks,
                merge_strategy=data.get("merge_strategy", "sequential"),
                coverage_targets=data.get("coverage_targets", []),
                decomposition_reason=data.get("decomposition_reason"),
                llm_confidence=0.8,
                validation_warnings=[],
                fallback_used=False
            )
        except Exception as e:
            logger.error(f"Failed to parse LLM decomposition response: {e}")
            return None
    
    def _heuristic_fallback(self, query: str, route: RouteDecision) -> DecompositionPlan:
        import re
        
        parts = re.split(r'\s+(?:and|or)\s+', query, flags=re.IGNORECASE)
        
        subtasks = []
        for i, part in enumerate(parts[:3], 1):
            subtasks.append(SubTask(
                id=f"task_{i}",
                type="retrieval",
                goal=f"Retrieve information for: {part[:50]}",
                query=part if part.endswith('?') else part + '?',
                depends_on=[],
                priority="high" if i == 1 else "medium"
            ))
        
        if route.intent == "comparison" and len(subtasks) >= 2:
            subtasks.append(SubTask(
                id=f"task_{len(subtasks)+1}",
                type="reasoning_prep",
                goal="Compare and synthesize results",
                query=f"Compare results from previous tasks",
                depends_on=[f"task_{i}" for i in range(1, len(subtasks)+1)],
                priority="high"
            ))
        
        return DecompositionPlan(
            subtasks=subtasks,
            merge_strategy="sequential",
            coverage_targets=[],
            decomposition_reason="Heuristic fallback decomposition",
            llm_confidence=0.5,
            validation_warnings=[],
            fallback_used=True
        )
