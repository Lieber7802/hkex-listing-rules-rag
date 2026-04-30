import re
from typing import List
from app.schemas.planning import RouteDecision, RouteValidationResult
from app.core.logger import logger


class HeuristicRouteValidator:
    def __init__(self):
        self.rule_number_pattern = re.compile(r'rule\s+\d+[A-Z]?\.\d+', re.IGNORECASE)
        self.comparison_keywords = ['compare', 'difference', 'versus', 'vs', 'differ']
        self.tool_keywords = ['calculate', 'ratio', 'percentage', 'size test', 'compute']
        self.multi_hop_keywords = ['and', 'or', 'both', 'as well as']
    
    def validate(self, decision: RouteDecision, query: str) -> RouteValidationResult:
        warnings: List[str] = []
        conflicts: List[str] = []
        
        query_lower = query.lower()
        
        if self._has_explicit_rule_number(query) and decision.intent == "comparison":
            conflicts.append("Query has explicit rule number but was classified as comparison")
            warnings.append("Rule number detected - should be rule_lookup, not comparison")
        
        if self._has_comparison_keywords(query) and decision.retrieval_strategy == "single_pass":
            conflicts.append("Query has comparison keywords but retrieval_strategy is single_pass")
            warnings.append("Comparison keywords detected - should use multi_query or targeted_iterative")
        
        if self._has_tool_keywords(query) and not decision.tool_decision.requires_tool:
            conflicts.append("Query has tool keywords but requires_tool is False")
            warnings.append("Tool keywords detected - should set requires_tool=True")
        
        if self._has_multi_hop_indicators(query) and decision.query_type == "direct":
            conflicts.append("Query has multi-hop indicators but query_type is direct")
            warnings.append("Multi-hop indicators detected - should be multi_hop")
        
        should_retry = len(conflicts) > 0 and len(conflicts) <= 2
        should_fallback = len(conflicts) > 2
        
        is_valid = len(conflicts) == 0
        
        if warnings:
            logger.info(f"Route validation warnings: {warnings}")
        
        return RouteValidationResult(
            is_valid=is_valid,
            warnings=warnings,
            conflicts=conflicts,
            should_retry=should_retry,
            should_fallback=should_fallback
        )
    
    def _has_explicit_rule_number(self, query: str) -> bool:
        return bool(self.rule_number_pattern.search(query))
    
    def _has_comparison_keywords(self, query: str) -> bool:
        return any(kw in query.lower() for kw in self.comparison_keywords)
    
    def _has_tool_keywords(self, query: str) -> bool:
        return any(kw in query.lower() for kw in self.tool_keywords)
    
    def _has_multi_hop_indicators(self, query: str) -> bool:
        query_lower = query.lower()
        count = sum(1 for kw in self.multi_hop_keywords if kw in query_lower)
        return count >= 2
