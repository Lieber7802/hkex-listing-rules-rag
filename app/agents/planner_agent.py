import re
import os
from typing import Any, List, Optional, Dict
from app.schemas.query import PlannerOutput
from app.core.config import settings
from app.core.logger import logger


class PlannerAgent:
    def __init__(self):
        self.multi_hop_indicators = [
            r'\band\b',
            r'\bor\b',
            r'\balso\b',
            r'\bas well as\b',
            r'\bcompare\b',
            r'\bdifference\b',
            r'\bboth\b',
            r'\bversus\b',
            r'\bvs\.?\b',
            r'\bhow (?:do|does|are|is) .* (?:relate|compare|differ|connect)',
            r'\bwhat (?:are|is) the (?:relationship|difference|connection)',
            r'\brequirements? for .* (?:and|or|plus)',
            r'\bimplications? of .* (?:and|or|plus)',
            # Chinese multi-hop indicators
            r'和|以及|还有|同时|另外|对比|比较|区别|差异',
        ]

        self.direct_indicators = [
            r'^what is',
            r'^what are',
            r'^define',
            r'^explain',
            r'^describe',
            r'^list',
            r'^state',
            r'^tell me about',
            r'^what does .* say',
            r'^what (?:is|are) the (?:requirement|rule|obligation)',
            r'^which rule',
            r'^which section',
            # Chinese direct indicators
            r'^什么是',
            r'^请解释',
            r'^请说明',
            r'^规则\d',
        ]

        self.intent_patterns = {
            'rule_lookup': [
                r'rule\s+\d+[A-Z]?\.\d+', r'what is rule', r'which rule',
                # Chinese
                r'规则\s*\d+[A-Z]?\.\d+', r'第\d+[A-Z]?条', r'条款\d+',
            ],
            'obligation_summary': [
                r'disclosure (?:obligation|requirement)', r'what (?:are|is) (?:the )?(?:disclosure|reporting)',
                # Chinese
                r'披露(?:义务|要求|规定)', r'信息披露', r'应当披露', r'须披露',
            ],
            'comparison': [
                r'compare', r'difference', r'versus', r'vs\.?', r'how .* differ',
                # Chinese
                r'对比', r'比较', r'区别', r'差异', r'不同.*地方',
            ],
            'eligibility_check': [
                r'threshold', r'eligib', r'qualif', r'size test',
                # Chinese
                r'门槛', r'阈值', r'测试', r'标准', r'是否符合', r'百分之',
            ],
            'procedure_flow': [
                r'procedure', r'process', r'step', r'how to', r'workflow',
                # Chinese
                r'程序', r'流程', r'步骤', r'如何', r'怎么', r'手续',
            ],
            'calculation_required': [
                r'calculate', r'ratio', r'percentage', r'compute',
                # Chinese
                r'计算', r'比率', r'百分比', r'比例', r'金额',
            ],
            'multi_condition': [r'and', r'as well as', r'both'],
        }

        self._llm_client = None
    
    def plan(self, query: str) -> PlannerOutput:
        query_lower = query.lower().strip()
        
        query_type = self._classify_query(query_lower)
        
        sub_queries = self._generate_sub_queries(query, query_type)
        
        needs_second_retrieval = self._needs_second_retrieval(query, query_type, sub_queries)
        
        reason = self._generate_reason(query_type, sub_queries, needs_second_retrieval)
        
        intent = self._classify_intent(query_lower)
        
        sub_tasks = self._extract_sub_tasks(query, query_type, sub_queries)
        
        retrieval_strategy = self._determine_retrieval_strategy(query_type, intent, needs_second_retrieval)
        
        requires_tool = self._requires_tool(intent, query_lower)

        evidence_requirements = self._build_evidence_requirements(sub_tasks, intent)

        answer_format = self._determine_answer_format(intent, query_type)

        tool_name = self._select_tool_name(intent, query_lower)
        tool_mode = self._select_tool_mode(intent)

        output = PlannerOutput(
            query_type=query_type,
            sub_queries=sub_queries,
            needs_second_retrieval=needs_second_retrieval,
            reason=reason,
            intent=intent,
            sub_tasks=sub_tasks,
            retrieval_strategy=retrieval_strategy,
            requires_tool=requires_tool,
            evidence_requirements=evidence_requirements,
            answer_format=answer_format,
            tool_name=tool_name,
            tool_mode=tool_mode,
        )
        
        logger.info(f"Planner classified query as '{query_type}' with intent '{intent}'")
        return output
    
    def _get_llm_client(self) -> Optional[Any]:
        """Get or initialize LLM client for intent classification fallback."""
        if self._llm_client is not None:
            return self._llm_client
        if settings.llm_provider in ["openai", "deepseek"]:
            try:
                from openai import OpenAI
                api_key = settings.llm_api_key or os.environ.get("OPENAI_API_KEY") or os.environ.get("DEEPSEEK_API_KEY")
                if api_key:
                    self._llm_client = OpenAI(api_key=api_key, base_url=settings.llm_base_url)
                    logger.info(f"PlannerAgent initialized LLM client for model: {settings.llm_model}")
            except ImportError:
                logger.warning("openai package not installed. LLM intent fallback disabled.")
        return self._llm_client

    def _classify_intent_with_llm(self, query: str) -> str:
        client = self._get_llm_client()
        if client is None:
            return "general"
        valid_intents = [
            "rule_lookup", "obligation_summary", "comparison",
            "eligibility_check", "procedure_flow", "calculation_required", "general"
        ]
        prompt = (
            "Classify the intent of this HKEX compliance query. "
            "Reply with exactly one word from: "
            "rule_lookup, obligation_summary, comparison, "
            "eligibility_check, procedure_flow, calculation_required, general\n\n"
            f"Query: {query}\nIntent:"
        )
        try:
            response = client.chat.completions.create(
                model=settings.llm_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=10,
                temperature=0.0,
            )
            raw = response.choices[0].message.content.strip().lower()
            # Sanitize: only allow alphanumeric and underscore
            result = re.sub(r'[^a-z_]', '', raw)
            if result in valid_intents:
                logger.info(f"LLM classified intent as '{result}' for query: {query[:60]}")
                return result
        except Exception as e:
            logger.warning(f"LLM intent classification failed: {e}")
        return "general"

    def _classify_intent(self, query_lower: str) -> str:
        priority_intents = ['comparison', 'calculation_required']
        for intent in priority_intents:
            if intent in self.intent_patterns:
                for pattern in self.intent_patterns[intent]:
                    if re.search(pattern, query_lower):
                        return intent

        for intent, patterns in self.intent_patterns.items():
            if intent in priority_intents:
                continue
            for pattern in patterns:
                if re.search(pattern, query_lower):
                    return intent

        return self._classify_intent_with_llm(query_lower)
    
    def _extract_sub_tasks(self, query: str, query_type: str, sub_queries: List[str]) -> List[str]:
        if query_type == "direct":
            return [query]
        return sub_queries if sub_queries else [query]
    
    def _determine_retrieval_strategy(self, query_type: str, intent: str, needs_second_retrieval: bool) -> str:
        if query_type == "direct":
            return "single_pass"
        if needs_second_retrieval or intent == "comparison":
            return "targeted_iterative"
        return "multi_query"
    
    def _requires_tool(self, intent: str, query_lower: str) -> bool:
        if intent == "calculation_required":
            return True
        if intent == "rule_lookup":
            return True
        if intent == "eligibility_check":
            return True
        tool_indicators = ['size test', 'ratio', 'calculate', 'percentage']
        return any(indicator in query_lower for indicator in tool_indicators)

    def _select_tool_name(self, intent: str, query_lower: str) -> Optional[str]:
        """Map intent to the appropriate tool name."""
        tool_map = {
            "calculation_required": "size_test_calculator",
            "rule_lookup": "rule_lookup",
            "eligibility_check": "transaction_classifier",
        }
        return tool_map.get(intent)

    def _select_tool_mode(self, intent: str) -> str:
        """Map intent to tool execution mode."""
        mode_map = {
            "calculation_required": "tool_only",
            "rule_lookup": "tool_plus_retrieval",
            "eligibility_check": "tool_plus_retrieval",
        }
        return mode_map.get(intent, "none")
    
    def _build_evidence_requirements(self, sub_tasks: List[str], intent: str) -> Dict[str, str]:
        if intent == "rule_lookup":
            level = "medium"
        elif intent in ["calculation_required", "comparison"]:
            level = "high"
        elif intent in ["eligibility_check", "procedure_flow"]:
            level = "high"
        elif intent == "obligation_summary":
            level = "high"
        else:
            level = "medium"
        return {task: level for task in sub_tasks}
    
    def _determine_answer_format(self, intent: str, query_type: str) -> str:
        if intent == "comparison":
            return "comparison_table"
        if intent == "procedure_flow":
            return "checklist_style"
        return "concise_with_citations"
    
    def _classify_query(self, query_lower: str) -> str:
        for pattern in self.direct_indicators:
            if re.search(pattern, query_lower):
                multi_hop_score = 0
                for pattern_mh in self.multi_hop_indicators:
                    if re.search(pattern_mh, query_lower):
                        multi_hop_score += 1
                
                if multi_hop_score >= 2:
                    return "multi_hop"
                return "direct"
        
        multi_hop_score = 0
        for pattern in self.multi_hop_indicators:
            if re.search(pattern, query_lower):
                multi_hop_score += 1
        
        if multi_hop_score >= 2:
            return "multi_hop"
        
        if " and " in query_lower or " or " in query_lower:
            clause_count = self._count_clauses(query_lower)
            if clause_count >= 2:
                return "multi_hop"
        
        return "direct"
    
    def _count_clauses(self, query: str) -> int:
        connectors = [' and ', ' or ', ' as well as ']
        count = 0
        for connector in connectors:
            count += query.count(connector)
        return count
    
    def _generate_sub_queries(self, query: str, query_type: str) -> List[str]:
        if query_type == "direct":
            return [query]
        
        sub_queries = []
        
        parts = re.split(r'\s+(?:and|or)\s+', query, flags=re.IGNORECASE)
        
        if len(parts) > 1:
            sub_queries.extend(parts)
        else:
            sub_queries.append(query)
        
        return sub_queries if sub_queries else [query]
    
    def _needs_second_retrieval(self, query: str, query_type: str, sub_queries: List[str]) -> bool:
        if query_type == "direct":
            return False
        
        if len(sub_queries) > 2:
            return True
        
        if any(word in query.lower() for word in ['compare', 'difference', 'versus', 'vs']):
            return True
        
        return False
    
    def _generate_reason(self, query_type: str, sub_queries: List[str], needs_second_retrieval: bool) -> str:
        if query_type == "direct":
            return "Single concept or clause lookup detected"
        
        reasons = []
        
        if len(sub_queries) > 1:
            reasons.append(f"Query decomposed into {len(sub_queries)} sub-queries")
        
        if needs_second_retrieval:
            reasons.append("Multiple retrieval passes may be needed for comprehensive answer")
        
        return "; ".join(reasons) if reasons else "Multi-hop reasoning required"


def plan_query(query: str) -> PlannerOutput:
    planner = PlannerAgent()
    return planner.plan(query)