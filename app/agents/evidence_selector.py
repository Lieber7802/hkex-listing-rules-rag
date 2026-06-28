from typing import List
from pydantic import BaseModel, Field

from app.schemas.query import PlannerOutput
from app.retrieval.hybrid_retriever import RetrievalResult
from app.core.logger import logger


class SelectedEvidence(BaseModel):
    selected_chunks: List[RetrievalResult] = Field(default_factory=list)
    diversity_score: float = Field(default=0.0)
    rule_coverage: List[str] = Field(default_factory=list)


def select_evidence(
    results: List[RetrievalResult],
    query_type: str = "direct",
    intent: str = "general",
    max_chunks: int = 5,
    prefer_rule_number: bool = True,
) -> SelectedEvidence:
    if query_type == "multi_hop":
        effective_max = 8
    elif intent in ("comparison", "procedure_flow"):
        effective_max = 6
    else:
        effective_max = max_chunks

    seen_ids = set()
    unique = []
    for r in results:
        if r.chunk_id not in seen_ids:
            seen_ids.add(r.chunk_id)
            unique.append(r)

    def priority_key(r: RetrievalResult) -> tuple:
        has_rule = 0 if (prefer_rule_number and r.chunk.rule_number) else 1
        return (has_rule, -r.score)

    sorted_chunks = sorted(unique, key=priority_key)
    selected = sorted_chunks[:effective_max]

    diversity = _calculate_diversity(selected)
    rule_coverage = _extract_rule_coverage(selected)

    evidence = SelectedEvidence(
        selected_chunks=selected,
        diversity_score=diversity,
        rule_coverage=rule_coverage,
    )
    logger.info(f"Selected {len(selected)}/{effective_max} chunks with diversity={diversity:.2f}")
    return evidence


def _calculate_diversity(selected: List[RetrievalResult]) -> float:
    if len(selected) <= 1:
        return 1.0
    unique_rules = {r.chunk.rule_number for r in selected if r.chunk.rule_number}
    unique_sections = {r.chunk.section_title for r in selected if r.chunk.section_title}
    rule_div = len(unique_rules) / len(selected) if selected else 0.0
    section_div = len(unique_sections) / len(selected) if selected else 0.0
    return (rule_div + section_div) / 2


def _extract_rule_coverage(selected: List[RetrievalResult]) -> List[str]:
    rules = []
    for r in selected:
        if r.chunk.rule_number and r.chunk.rule_number not in rules:
            rules.append(r.chunk.rule_number)
    return rules


class EvidenceSelector:
    def __init__(self, max_chunks: int = 5, prefer_rule_number: bool = True):
        self.max_chunks = max_chunks
        self.prefer_rule_number = prefer_rule_number

    def select(self, plan: PlannerOutput, results: List[RetrievalResult]) -> SelectedEvidence:
        return select_evidence(
            results,
            query_type=plan.query_type,
            intent=plan.intent,
            max_chunks=self.max_chunks,
            prefer_rule_number=self.prefer_rule_number,
        )
