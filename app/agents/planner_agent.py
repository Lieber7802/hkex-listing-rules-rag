import re
from typing import Any, List, Optional, Dict
from app.schemas.query import PlannerOutput
from app.core.config import settings
from app.core.llm_client import get_llm_client
from app.core.logger import logger


class PlannerAgent:
    _CHECKLIST_REQUIRED_FIELDS = {
        "classification",
        "is_connected",
        "shareholder_vote_required",
    }
    _CHECKLIST_CLASSIFICATIONS = (
        ("very_substantial", (
            r"\bvery substantial (?:acquisition|disposal|transaction)\b",
            r"\u975e\u5e38\u91cd\u5927(?:\u7684)?(?:\u6536\u8d2d|\u51fa\u552e|\u4ea4\u6613)",
        )),
        ("major_transaction", (
            r"\bmajor transaction\b",
            r"\u4e3b\u8981\u4ea4\u6613",
        )),
        ("discloseable_transaction", (
            r"\bdiscloseable transaction\b",
            r"(?:\u987b\u4e88|\u9808\u4e88)\u62ab\u9732(?:\u7684)?\u4ea4\u6613",
        )),
        ("share_transaction", (
            r"\bshare transaction\b",
            r"\u80a1\u4efd\u4ea4\u6613",
        )),
        ("de_minimis", (
            r"\bde minimis(?: transaction)?\b",
            r"(?:\u5fae\u5c0f|\u6700\u4f4e\u9650\u5ea6)\u4ea4\u6613",
        )),
    )
    _REGULATORY_GROUNDS_TERMS = (
        "disclosure", "announce", "announcement", "approval", "obligation",
        "requirement", "applicable rule", "applicable rules", "consequence",
        "consequences", "legal basis", "why", "disclose", "circular",
        "\u62ab\u9732", "\u516c\u544a", "\u6279\u51c6", "\u80a1\u4e1c\u6279\u51c6", "\u4e49\u52a1",
        "\u89c4\u5219", "\u540e\u679c", "\u9002\u7528", "\u901a\u51fd",
    )

    def __init__(self, tool_evidence_policy: str = "regulatory_grounded"):
        if tool_evidence_policy not in {"legacy", "regulatory_grounded"}:
            raise ValueError(f"unsupported tool evidence policy: {tool_evidence_policy}")
        self.tool_evidence_policy = tool_evidence_policy
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
                r'\bsummarize\b.*\b(?:obligation|compliance|disclosure)',
                r'\b(?:obligation|compliance)\b.*\b(?:summary|summarize|requirement)',
                r'\bwhat follows?\b.*\b(?:under|pursuant to|according to)\b.*\bchapter\s*14[a-z]?\b',
                r'\b(?:consequences?|next steps?|what happens?)\b.*\b(?:under|pursuant to|according to)\b.*\bchapter\s*14[a-z]?\b',
                r'(?:\u7b2c?\s*14[a-z]?\s*\u7ae0?|\u7b2c?\s*14[a-z]?\s*\u7ae0?\u89c4\u5219).*(?:\u540e\u679c|\u540e\u7eed|\u63a5\u4e0b\u6765|\u9700\u8981(?:\u505a|\u5c65\u884c|\u91c7\u53d6)|\u600e\u4e48\u529e|\u5982\u4f55\u5904\u7406)',
                r'(?:\u6839\u636e|\u4f9d\u7167|\u6309|\u6309\u7167).*(?:\u7b2c?\s*14[a-z]?\s*\u7ae0?).*(?:\u540e\u679c|\u540e\u7eed|\u63a5\u4e0b\u6765|\u9700\u8981(?:\u505a|\u5c65\u884c|\u91c7\u53d6)|\u600e\u4e48\u529e|\u5982\u4f55\u5904\u7406)',
                "\u6982\u62ec.*(?:\u62ab\u9732|\u5408\u89c4|\u4e49\u52a1|\u8981\u6c42)",
                "(?:\u62ab\u9732|\u5408\u89c4)\u4e49\u52a1",
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
                r'\bcalculate\b', r'\bratios?\b', r'\bpercentages?\b', r'\bcompute\b',
                # Chinese
                r'计算', r'比率', r'百分比', r'比例', r'金额',
            ],
            'multi_condition': [r'and', r'as well as', r'both'],
        }
    
    def plan(self, query: str, *, use_llm: bool = True) -> PlannerOutput:
        query_lower = query.lower().strip()
        
        query_type = self._classify_query(query_lower)
        
        sub_queries = self._generate_sub_queries(query, query_type)
        
        needs_second_retrieval = self._needs_second_retrieval(query, query_type, sub_queries)
        
        reason = self._generate_reason(query_type, sub_queries, needs_second_retrieval)
        
        intent, planner_reason, fallback_used = self._classify_intent(
            query_lower, use_llm=use_llm
        )
        guarded_intent = self._apply_intent_guardrails(intent, query_lower)
        if guarded_intent != intent:
            planner_reason = (
                f"{planner_reason}; deterministic query semantics corrected "
                f"{intent} to {guarded_intent}"
            )
            intent = guarded_intent
        if intent == "calculation_required" and query_type != "direct":
            # Calculation inputs often contain several "and" clauses. They
            # are one tool workflow, not independent regulatory sub-questions.
            query_type = "direct"
            sub_queries = [query]
            needs_second_retrieval = False
            reason = f"{reason}; calculation workflow kept as one tool query"
        if planner_reason:
            reason = f"{reason}; {planner_reason}"
        
        sub_tasks = self._extract_sub_tasks(query, query_type, sub_queries)
        
        retrieval_strategy = self._determine_retrieval_strategy(query_type, intent, needs_second_retrieval)
        
        tool_name = self._select_tool_name(intent, query_lower)
        requires_tool = self._requires_tool(intent, query_lower) and tool_name is not None

        evidence_requirements = self._build_evidence_requirements(sub_tasks, intent)

        answer_format = self._determine_answer_format(intent, query_type)

        tool_mode = self._select_tool_mode(intent, query_lower)
        if intent == "obligation_summary" and not requires_tool:
            # Generic consequence questions need source retrieval, but the
            # checklist tool cannot safely infer its required legal facts.
            tool_name = None
            tool_mode = "none"
            reason = (
                f"{reason}; obligation summary routed retrieval-only because "
                "the checklist inputs are not all explicit"
            )

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
        
        logger.info(
            "Planner classified query as '%s' with intent '%s' (fallback=%s)",
            query_type, intent, fallback_used,
        )
        return output
    
    def _get_llm_client(self) -> Optional[Any]:
        return get_llm_client()

    def _classify_intent_with_llm(self, query: str) -> Optional[str]:
        client = self._get_llm_client()
        if client is None:
            return None
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
        return None

    def _classify_intent_heuristically(self, query_lower: str) -> str:
        priority_intents = [
            'comparison', 'calculation_required', 'procedure_flow',
            'obligation_summary',
        ]
        for intent in priority_intents:
            if intent in self.intent_patterns:
                for pattern in self.intent_patterns[intent]:
                    if re.search(pattern, query_lower, flags=re.IGNORECASE):
                        return intent

        for intent, patterns in self.intent_patterns.items():
            if intent in priority_intents:
                continue
            for pattern in patterns:
                if re.search(pattern, query_lower, flags=re.IGNORECASE):
                    return intent

        return "general"

    def _apply_intent_guardrails(self, intent: str, query_lower: str) -> str:
        """Correct only unambiguous lexical conflicts after LLM classification.

        LLM planning remains primary. These guards prevent known category
        errors such as matching ``ratio`` inside ``registration`` and prevent
        an explicit procedure/obligation request from being collapsed into a
        generic rule lookup merely because it cites a rule number.
        """
        if self._matches_any(self.intent_patterns['comparison'], query_lower):
            return 'comparison'
        if self._matches_any(self.intent_patterns['calculation_required'], query_lower):
            return 'calculation_required'
        if self._matches_any(self.intent_patterns['procedure_flow'], query_lower):
            return 'procedure_flow'
        if self._matches_any(self.intent_patterns['obligation_summary'], query_lower):
            return 'obligation_summary'
        if self._matches_any(self.intent_patterns['rule_lookup'], query_lower):
            return 'rule_lookup'
        return intent

    @staticmethod
    def _matches_any(patterns: List[str], query_lower: str) -> bool:
        return any(re.search(pattern, query_lower, flags=re.IGNORECASE) for pattern in patterns)

    def _classify_intent(
        self, query_lower: str, *, use_llm: bool
    ) -> tuple[str, str, bool]:
        """Use the LLM as the primary semantic router with deterministic fallback.

        The heuristic remains deliberately available for offline tests, provider
        failures, and malformed model output.  It is not silently bypassed:
        callers can expose the fallback in the route audit trail.
        """
        if use_llm:
            llm_intent = self._classify_intent_with_llm(query_lower)
            if llm_intent is not None:
                return llm_intent, "Intent selected by LLM planner", False

        heuristic_intent = self._classify_intent_heuristically(query_lower)
        reason = (
            "LLM planner unavailable or invalid; heuristic fallback selected intent"
            if use_llm
            else "Heuristic planner explicitly selected"
        )
        return heuristic_intent, reason, use_llm
    
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
        if intent == "obligation_summary":
            return self._has_complete_checklist_inputs(query_lower)
        return bool(re.search(
            r'\b(?:size test|ratios?|calculate|percentages?)\b', query_lower,
            flags=re.IGNORECASE,
        ))

    def _select_tool_name(self, intent: str, query_lower: str) -> Optional[str]:
        """Map intent to the appropriate tool name."""
        tool_map = {
            "calculation_required": "size_test_calculator",
            "rule_lookup": "rule_lookup",
            "eligibility_check": "transaction_classifier",
            "obligation_summary": "disclosure_checklist",
        }
        return tool_map.get(intent)

    def _select_tool_mode(self, intent: str, query_lower: str = "") -> str:
        """Map intent to tool execution mode."""
        if intent == "obligation_summary":
            if not self._has_complete_checklist_inputs(query_lower):
                return "none"
            return (
                "tool_plus_retrieval"
                if self.tool_evidence_policy == "regulatory_grounded"
                else "tool_only"
            )
        if self.tool_evidence_policy == "regulatory_grounded":
            if intent == "calculation_required":
                return (
                    "tool_plus_retrieval"
                    if self._requires_regulatory_grounding(query_lower)
                    else "tool_only"
                )
        mode_map = {
            "calculation_required": "tool_only",
            "rule_lookup": "tool_plus_retrieval",
            "eligibility_check": "tool_plus_retrieval",
        }
        return mode_map.get(intent, "none")

    def _has_complete_checklist_inputs(self, query_lower: str) -> bool:
        """Return whether the query explicitly supplies every checklist input.

        The checklist requires a classification, connected-transaction status,
        and shareholder-vote requirement.  This method intentionally does not
        invent legal defaults: without all three facts, retrieval is safer.
        """
        return self._CHECKLIST_REQUIRED_FIELDS.issubset(
            self._extract_explicit_checklist_inputs(query_lower)
        )

    def _extract_explicit_checklist_inputs(self, query_lower: str) -> Dict[str, Any]:
        inputs: Dict[str, Any] = {}
        for classification, patterns in self._CHECKLIST_CLASSIFICATIONS:
            if self._matches_any(list(patterns), query_lower):
                inputs["classification"] = classification
                break

        if re.search(
            r"\b(?:not|non)[ -]?(?:a )?connected(?: transaction)?\b|"
            r"\bnot related(?: party)?\b|(?:\u975e|\u4e0d(?:\u662f|\u5c5e\u4e8e)?|\u5e76\u975e)(?:\u5173\u8054|\u95dc\u806f)",
            query_lower,
            flags=re.IGNORECASE,
        ):
            inputs["is_connected"] = False
        elif re.search(
            r"\b(?:connected transaction|connected party|related party|associate)\b|"
            r"(?:\u5173\u8054|\u95dc\u806f)(?:\u4ea4\u6613|\u4eba\u58eb|\u65b9)",
            query_lower,
            flags=re.IGNORECASE,
        ):
            inputs["is_connected"] = True

        if re.search(
            r"\b(?:no|not|without)\s+(?:shareholder(?:s')?\s+)?(?:vote|approval)\s+(?:is\s+)?required\b|"
            r"\bshareholder(?:s')?\s+(?:vote|approval)\s+(?:is\s+)?not\s+required\b|"
            r"(?:\u65e0\u9700|\u7121\u9700|\u4e0d\u9700\u8981)(?:\u80a1\u4e1c|\u80a1\u6771)(?:\u6279\u51c6|\u5be9\u6279|\u5ba1\u6279|\u6295\u7968)",
            query_lower,
            flags=re.IGNORECASE,
        ):
            inputs["shareholder_vote_required"] = False
        elif re.search(
            r"\b(?:shareholder(?:s')?\s+)?(?:vote|approval)\s+(?:is\s+)?required\b|"
            r"\brequires?\s+(?:shareholder(?:s')?\s+)?(?:vote|approval)\b|"
            r"(?:\u9700\u8981|\u987b|\u9808)(?:\u80a1\u4e1c|\u80a1\u6771)(?:\u6279\u51c6|\u5be9\u6279|\u5ba1\u6279|\u6295\u7968)|"
            r"(?:\u80a1\u4e1c|\u80a1\u6771)(?:\u6279\u51c6|\u5be9\u6279|\u5ba1\u6279|\u6295\u7968)(?:\u8981\u6c42|\u5fc5\u987b|\u5fc5\u9808|\u9700\u8981)",
            query_lower,
            flags=re.IGNORECASE,
        ):
            inputs["shareholder_vote_required"] = True

        return inputs

    def _requires_regulatory_grounding(self, query_lower: str) -> bool:
        return any(term in query_lower for term in self._REGULATORY_GROUNDS_TERMS)
    
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
