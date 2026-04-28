from typing import List
from pydantic import BaseModel, Field

from app.schemas.query import PlannerOutput
from app.retrieval.hybrid_retriever import RetrievalResult
from app.core.logger import logger


class SelectedEvidence(BaseModel):
    selected_chunks: List[RetrievalResult] = Field(default_factory=list)
    diversity_score: float = Field(default=0.0)
    rule_coverage: List[str] = Field(default_factory=list)


class EvidenceSelector:
    def __init__(self, max_chunks: int = 5, prefer_rule_number: bool = True):
        self.max_chunks = max_chunks
        self.prefer_rule_number = prefer_rule_number
    
    def select(self, plan: PlannerOutput, results: List[RetrievalResult]) -> SelectedEvidence:
        effective_max_chunks = self._determine_max_chunks(plan)
        deduplicated = self._deduplicate(results)
        sorted_chunks = self._sort_by_priority(deduplicated)
        selected = sorted_chunks[:effective_max_chunks]
        diversity_score = self._calculate_diversity(selected)
        rule_coverage = self._extract_rule_coverage(selected)

        evidence = SelectedEvidence(
            selected_chunks=selected,
            diversity_score=diversity_score,
            rule_coverage=rule_coverage
        )

        logger.info(f"Selected {len(selected)}/{effective_max_chunks} chunks with diversity={diversity_score:.2f}")
        return evidence

    def _determine_max_chunks(self, plan: PlannerOutput) -> int:
        if plan.query_type == "multi_hop":
            return 8
        if plan.intent in ["comparison", "procedure_flow"]:
            return 6
        return self.max_chunks
    
    def _deduplicate(self, results: List[RetrievalResult]) -> List[RetrievalResult]:
        seen_ids = set()
        unique = []
        for result in results:
            if result.chunk_id not in seen_ids:
                seen_ids.add(result.chunk_id)
                unique.append(result)
        return unique
    
    def _sort_by_priority(self, results: List[RetrievalResult]) -> List[RetrievalResult]:
        def priority_key(r: RetrievalResult) -> tuple:
            has_rule_number = 0 if (self.prefer_rule_number and r.chunk.rule_number) else 1
            return (has_rule_number, -r.score)
        return sorted(results, key=priority_key)
    
    def _calculate_diversity(self, selected: List[RetrievalResult]) -> float:
        if len(selected) <= 1:
            return 1.0
        unique_rules = set()
        unique_sections = set()
        for result in selected:
            if result.chunk.rule_number:
                unique_rules.add(result.chunk.rule_number)
            if result.chunk.section_title:
                unique_sections.add(result.chunk.section_title)
        rule_diversity = len(unique_rules) / len(selected) if selected else 0.0
        section_diversity = len(unique_sections) / len(selected) if selected else 0.0
        return (rule_diversity + section_diversity) / 2
    
    def _extract_rule_coverage(self, selected: List[RetrievalResult]) -> List[str]:
        rules = []
        for result in selected:
            if result.chunk.rule_number and result.chunk.rule_number not in rules:
                rules.append(result.chunk.rule_number)
        return rules
