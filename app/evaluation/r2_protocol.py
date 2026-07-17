from __future__ import annotations

import re
from collections import defaultdict
from difflib import SequenceMatcher
from typing import Iterable, List

from pydantic import Field

from app.evaluation.schemas import BenchmarkCase, StrictModel
from app.evaluation.source_registry import normalize_text


class BenchmarkIsolationIssue(StrictModel):
    case_id: str
    reference_case_id: str
    issue_type: str
    similarity: float | None = Field(default=None, ge=0.0, le=1.0)


class BenchmarkIsolationReport(StrictModel):
    candidate_case_count: int
    reference_case_count: int
    query_overlap_count: int
    multi_source_overlap_count: int
    issues: List[BenchmarkIsolationIssue] = Field(default_factory=list)
    passed: bool


def validate_benchmark_isolation(
    candidates: Iterable[BenchmarkCase],
    reference_cases: Iterable[BenchmarkCase],
    duplicate_threshold: float = 0.90,
) -> BenchmarkIsolationReport:
    candidate_list = list(candidates)
    reference_list = list(reference_cases)
    reference_queries = [
        (_case_query(case), _query_tokens(_case_query(case)))
        for case in reference_list
    ]
    reference_multi_sources = defaultdict(list)
    for reference in reference_list:
        signature = _multi_source_signature(reference)
        if signature:
            reference_multi_sources[signature].append(reference.case_id)

    issues: List[BenchmarkIsolationIssue] = []
    query_overlap_count = 0
    multi_source_overlap_count = 0

    for candidate in candidate_list:
        candidate_query = _case_query(candidate)
        candidate_tokens = _query_tokens(candidate_query)
        candidate_sources = _multi_source_signature(candidate)
        for reference, (reference_query, reference_tokens) in zip(reference_list, reference_queries):
            similarity = _query_similarity_cached(
                candidate_query, candidate_tokens, reference_query, reference_tokens,
                duplicate_threshold,
            )
            if similarity >= duplicate_threshold:
                query_overlap_count += 1
                issues.append(BenchmarkIsolationIssue(
                    case_id=candidate.case_id,
                    reference_case_id=reference.case_id,
                    issue_type="near_duplicate_query",
                    similarity=round(similarity, 6),
                ))
        if candidate_sources:
            for reference_case_id in reference_multi_sources.get(candidate_sources, []):
                multi_source_overlap_count += 1
                issues.append(BenchmarkIsolationIssue(
                    case_id=candidate.case_id,
                    reference_case_id=reference_case_id,
                    issue_type="reused_multi_source_combination",
                ))

    return BenchmarkIsolationReport(
        candidate_case_count=len(candidate_list),
        reference_case_count=len(reference_list),
        query_overlap_count=query_overlap_count,
        multi_source_overlap_count=multi_source_overlap_count,
        issues=issues,
        passed=not issues,
    )


def _case_query(case: BenchmarkCase) -> str:
    if case.turns:
        return "\n".join(turn.query for turn in case.turns)
    return case.query or ""


def _multi_source_signature(case: BenchmarkCase) -> tuple[str, ...] | None:
    source_ids = tuple(sorted(case.source_chunk_ids))
    return source_ids if len(source_ids) > 1 else None


def _query_similarity(left: str, right: str) -> float:
    left_normalized = normalize_text(left)
    right_normalized = normalize_text(right)
    if not left_normalized or not right_normalized:
        return 0.0
    left_tokens = _query_tokens(left_normalized)
    right_tokens = _query_tokens(right_normalized)
    union = left_tokens | right_tokens
    jaccard = len(left_tokens & right_tokens) / len(union) if union else 0.0
    sequence = SequenceMatcher(None, left_normalized, right_normalized, autojunk=False).ratio()
    return max(sequence, jaccard)


def _query_similarity_cached(
    left_normalized: str,
    left_tokens: set[str],
    right_normalized: str,
    right_tokens: set[str],
    duplicate_threshold: float,
) -> float:
    if not left_normalized or not right_normalized:
        return 0.0
    union = left_tokens | right_tokens
    jaccard = len(left_tokens & right_tokens) / len(union) if union else 0.0
    if jaccard >= duplicate_threshold:
        return jaccard

    matcher = SequenceMatcher(None, left_normalized, right_normalized, autojunk=False)
    # `real_quick_ratio` and `quick_ratio` are documented upper bounds for
    # the full ratio. They cheaply eliminate the overwhelmingly dissimilar
    # generated pairs before the quadratic comparison.
    if matcher.real_quick_ratio() < duplicate_threshold:
        return jaccard
    if matcher.quick_ratio() < duplicate_threshold:
        return jaccard
    return max(matcher.ratio(), jaccard)


def _query_tokens(normalized_query: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]", normalized_query))
