import re
from typing import List, Optional
from pydantic import BaseModel, Field

from app.agents.coverage_checker import _tokenize_mixed
from app.schemas.query import PlannerOutput
from app.retrieval.hybrid_retriever import RetrievalResult
from app.core.logger import logger


_MIN_SUBTASK_RELEVANCE = 0.25
_GENERIC_SUBTASK_TERMS = {
    "answer", "answers", "compare", "comparison", "context", "contexts",
    "evidence", "identify", "passage", "passages", "relationship", "rule",
    "rules", "grounded", "hkex", "main", "board", "gem", "transaction",
}
_RULE_REFERENCE_RE = re.compile(
    r"\brule\s+(\d+[a-z]?(?:\.\d+[a-z]?)?)\b", re.IGNORECASE,
)


class SelectedEvidence(BaseModel):
    selected_chunks: List[RetrievalResult] = Field(default_factory=list)
    diversity_score: float = Field(default=0.0)
    rule_coverage: List[str] = Field(default_factory=list)
    requested_subtasks: List[str] = Field(default_factory=list)
    covered_subtasks: List[str] = Field(default_factory=list)
    uncovered_subtasks: List[str] = Field(default_factory=list)
    selection_budget: int = Field(default=0)


def select_evidence(
    results: List[RetrievalResult],
    query_type: str = "direct",
    intent: str = "general",
    max_chunks: int = 5,
    prefer_rule_number: bool = True,
    selection_policy: str = "legacy",
    sub_tasks: Optional[List[str]] = None,
) -> SelectedEvidence:
    if selection_policy not in {"legacy", "coverage_aware"}:
        raise ValueError(f"unsupported evidence selection policy: {selection_policy}")

    tasks = list(sub_tasks or [])
    effective_max = _selection_budget(
        query_type, intent, max_chunks, selection_policy, tasks,
    )
    unique = _deduplicate_results(results)

    if selection_policy == "coverage_aware":
        selected, covered_tasks = _select_with_subtask_coverage(
            unique, tasks, effective_max, prefer_rule_number,
        )
    else:
        selected = sorted(unique, key=lambda result: _priority_key(
            result, prefer_rule_number,
        ))[:effective_max]
        covered_tasks = []

    diversity = _calculate_diversity(selected)
    rule_coverage = _extract_rule_coverage(selected)

    evidence = SelectedEvidence(
        selected_chunks=selected,
        diversity_score=diversity,
        rule_coverage=rule_coverage,
        requested_subtasks=tasks,
        covered_subtasks=covered_tasks,
        uncovered_subtasks=[task for task in tasks if task not in covered_tasks],
        selection_budget=effective_max,
    )
    logger.info(
        "Selected %s/%s chunks with diversity=%.2f policy=%s covered_subtasks=%s/%s",
        len(selected), effective_max, diversity, selection_policy,
        len(covered_tasks), len(tasks),
    )
    return evidence


def _selection_budget(
    query_type: str,
    intent: str,
    max_chunks: int,
    selection_policy: str,
    sub_tasks: List[str],
) -> int:
    if selection_policy == "coverage_aware":
        if query_type == "multi_hop" or intent in {"comparison", "procedure_flow"} or len(sub_tasks) > 1:
            return max(max_chunks, 8)
        return max_chunks
    if query_type == "multi_hop":
        return 8
    if intent in ("comparison", "procedure_flow"):
        return 6
    return max_chunks


def _deduplicate_results(results: List[RetrievalResult]) -> List[RetrievalResult]:
    seen_ids = set()
    unique = []
    for result in results:
        if result.chunk_id not in seen_ids:
            seen_ids.add(result.chunk_id)
            unique.append(result)
    return unique


def _priority_key(result: RetrievalResult, prefer_rule_number: bool) -> tuple:
    has_rule = 0 if (prefer_rule_number and result.chunk.rule_number) else 1
    return has_rule, -result.score, result.chunk_id


def _select_with_subtask_coverage(
    results: List[RetrievalResult],
    sub_tasks: List[str],
    effective_max: int,
    prefer_rule_number: bool,
) -> tuple[List[RetrievalResult], List[str]]:
    selected: List[RetrievalResult] = []
    selected_ids = set()
    covered_tasks: List[str] = []

    for task in sub_tasks:
        candidates = sorted(
            (
                result for result in results
                if (
                    result.chunk_id not in selected_ids
                    and _subtask_relevance(task, result) >= _MIN_SUBTASK_RELEVANCE
                )
            ),
            key=lambda result: (-_subtask_relevance(task, result), *_priority_key(
                result, prefer_rule_number,
            )),
        )
        if not candidates or len(selected) >= effective_max:
            continue
        selected.append(candidates[0])
        selected_ids.add(candidates[0].chunk_id)
        covered_tasks.append(task)

    remaining = [result for result in results if result.chunk_id not in selected_ids]
    for require_new_topic in (True, False):
        selected_topics = {_topic_key(result) for result in selected}
        for result in sorted(remaining, key=lambda item: _priority_key(item, prefer_rule_number)):
            if len(selected) >= effective_max:
                break
            if result.chunk_id in selected_ids:
                continue
            if require_new_topic and _topic_key(result) in selected_topics:
                continue
            selected.append(result)
            selected_ids.add(result.chunk_id)
            selected_topics.add(_topic_key(result))

    return selected, covered_tasks


def _subtask_relevance(sub_task: str, result: RetrievalResult) -> float:
    chunk = result.chunk
    searchable_text = " ".join(filter(None, [
        chunk.rule_number, chunk.section_title, chunk.text,
    ])).lower()
    task_rules = _referenced_rules(sub_task)
    if chunk.rule_number and chunk.rule_number.lower() in task_rules:
        # An exact, explicitly requested rule is stronger evidence than a
        # coincidental shared word in a long sub-task description.
        return 2.0

    task_tokens = _meaningful_subtask_tokens(sub_task)
    text_tokens = _meaningful_subtask_tokens(searchable_text)
    if not task_tokens:
        return 0.0
    return len(task_tokens & text_tokens) / len(task_tokens)


def _referenced_rules(text: str) -> set[str]:
    return {
        match.group(1).lower()
        for match in _RULE_REFERENCE_RE.finditer(text)
    }


def _meaningful_subtask_tokens(text: str) -> set[str]:
    """Keep specific English/CJK terms while removing task-template language."""
    english = {
        token.lower()
        for token in re.findall(r"[A-Za-z][A-Za-z0-9]*", text)
        if len(token) > 1
    }
    chinese = {
        token for token in _tokenize_mixed(text)
        if any("\u4e00" <= char <= "\u9fff" for char in token)
    }
    return (english | chinese) - _GENERIC_SUBTASK_TERMS


def _topic_key(result: RetrievalResult) -> str:
    chunk = result.chunk
    return chunk.rule_number or chunk.section_title or chunk.chunk_id


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
    def __init__(
        self,
        max_chunks: int = 5,
        prefer_rule_number: bool = True,
        selection_policy: str = "legacy",
    ):
        self.max_chunks = max_chunks
        self.prefer_rule_number = prefer_rule_number
        self.selection_policy = selection_policy

    def select(self, plan: PlannerOutput, results: List[RetrievalResult]) -> SelectedEvidence:
        return select_evidence(
            results,
            query_type=plan.query_type,
            intent=plan.intent,
            max_chunks=self.max_chunks,
            prefer_rule_number=self.prefer_rule_number,
            selection_policy=self.selection_policy,
            sub_tasks=plan.sub_tasks or plan.sub_queries,
        )
