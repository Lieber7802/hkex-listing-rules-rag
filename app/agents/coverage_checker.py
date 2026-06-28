import re
from typing import List, Dict, Optional, Set
from pydantic import BaseModel, Field

from app.schemas.query import PlannerOutput
from app.schemas.document import Chunk
from app.retrieval.hybrid_retriever import RetrievalResult
from app.core.logger import logger


_EN_STOP_WORDS = {'the', 'a', 'an', 'and', 'or', 'of', 'to', 'in', 'for', 'on', 'with', 'by'}
_ZH_STOP_CHARS = set('的了是在和与这那有为等及或但而')


def _tokenize_mixed(text: str) -> Set[str]:
    """Tokenize mixed Chinese/English text.

    English: space-split words, filtered by stop words.
    Chinese: character bigrams (相邻双字), filtered by stop characters.
    Combined tokens are returned as a set.
    """
    tokens: Set[str] = set()

    # English tokens: extract space-separated words
    eng_tokens = text.split()
    for token in eng_tokens:
        if token.lower() not in _EN_STOP_WORDS and len(token) > 1:
            tokens.add(token.lower())

    # Chinese tokens: character bigrams
    zh_chars = [c for c in text if '\u4e00' <= c <= '\u9fff']
    for i in range(len(zh_chars) - 1):
        bigram = zh_chars[i] + zh_chars[i + 1]
        # Skip if either char is a stop character
        if zh_chars[i] in _ZH_STOP_CHARS or zh_chars[i + 1] in _ZH_STOP_CHARS:
            continue
        tokens.add(bigram)

    return tokens


class CoverageAssessment(BaseModel):
    sub_task_coverage: Dict[str, bool] = Field(default_factory=dict)
    missing_information: List[str] = Field(default_factory=list)
    coverage_score: float = Field(default=0.0)
    needs_targeted_retrieval: bool = Field(default=False)
    retrieval_targets: List[str] = Field(default_factory=list)
    score_strategy: Optional[str] = Field(default=None, description="Score strategy used: 'bm25', 'dense', or 'fused'")


class CoverageChecker:
    def __init__(self, min_support_score: float = 0.6, min_chunks_per_task: int = 1):
        self.min_support_score = min_support_score
        self.min_chunks_per_task = min_chunks_per_task
    
    def assess(self, plan: PlannerOutput, results: List[RetrievalResult], intent: Optional[str] = None) -> CoverageAssessment:
        """Assess coverage of sub-tasks by retrieved chunks.

        Args:
            plan: The query plan containing sub-tasks
            results: Retrieved chunks
            intent: Query intent for score selection (e.g., 'rule_lookup', 'obligation_summary')

        Returns:
            Coverage assessment with scores and missing information
        """
        sub_task_coverage: Dict[str, bool] = {}
        missing_information: List[str] = []
        retrieval_targets: List[str] = []

        for sub_task in plan.sub_tasks:
            supporting_chunks = self._find_supporting_chunks(sub_task, results, intent)
            is_covered = len(supporting_chunks) >= self.min_chunks_per_task
            sub_task_coverage[sub_task] = is_covered

            if not is_covered:
                missing_information.append(sub_task)
                retrieval_targets.append(sub_task)
        
        total_tasks = len(plan.sub_tasks)
        covered_tasks = sum(1 for v in sub_task_coverage.values() if v)
        coverage_score = covered_tasks / total_tasks if total_tasks > 0 else 0.0

        needs_targeted_retrieval = len(missing_information) > 0

        # Determine score strategy used
        score_strategy = "fused"  # default
        if intent == "rule_lookup":
            score_strategy = "bm25"
        elif intent == "obligation_summary":
            score_strategy = "dense"

        assessment = CoverageAssessment(
            sub_task_coverage=sub_task_coverage,
            missing_information=missing_information,
            coverage_score=coverage_score,
            needs_targeted_retrieval=needs_targeted_retrieval,
            retrieval_targets=retrieval_targets,
            score_strategy=score_strategy
        )
        
        logger.info(f"Coverage assessment: {covered_tasks}/{total_tasks} tasks covered, score={coverage_score:.2f}")
        return assessment
    
    def _find_supporting_chunks(self, sub_task: str, results: List[RetrievalResult], intent: Optional[str] = None) -> List[RetrievalResult]:
        """Find chunks that support a given sub-task.

        Args:
            sub_task: The sub-task to find support for
            results: List of retrieval results to search through
            intent: Query intent (e.g., 'rule_lookup', 'obligation_summary')

        Returns:
            List of supporting retrieval results
        """
        supporting = []

        # Detect if sub_task contains specific rule references
        has_rule_ref = bool(re.search(r'\b\d+[A-Z]?\.\d+\b', sub_task))

        for result in results:
            # Choose score based on query type
            if intent == "rule_lookup" or has_rule_ref:
                # For rule-specific queries, prioritize BM25 (lexical match)
                base_score = result.bm25_score
                threshold = 0.5  # Stricter threshold for lexical matching
            elif intent == "obligation_summary":
                # For conceptual queries, prioritize dense (semantic match)
                base_score = result.dense_score
                threshold = self.min_support_score
            else:
                # Default: use fused score
                base_score = result.score
                threshold = self.min_support_score

            if base_score < threshold:
                continue

            if self._is_relevant(sub_task, result.chunk, result):
                supporting.append(result)

        logger.debug(f"Found {len(supporting)} supporting chunks for sub-task: {sub_task[:50]}...")
        return supporting
    
    def _is_relevant(self, sub_task: str, chunk: Chunk, result: RetrievalResult) -> bool:
        """Determine if a chunk is relevant to a sub-task using multi-signal matching.

        Args:
            sub_task: The sub-task text
            chunk: The chunk to evaluate
            result: The retrieval result containing scores

        Returns:
            True if chunk is relevant to sub-task
        """
        # Signal 1: Exact rule number match (highest priority)
        if chunk.rule_number and self._match_rule_number(sub_task, chunk.rule_number):
            logger.debug(f"Chunk {chunk.chunk_id} matched by rule_number: {chunk.rule_number}")
            return True

        # Signal 2: Section title semantic match
        if chunk.section_title and self._match_section_title(sub_task, chunk.section_title):
            logger.debug(f"Chunk {chunk.chunk_id} matched by section_title: {chunk.section_title}")
            return True

        # Signal 3: Text overlap score (fallback)
        text_score = self._text_overlap_score(sub_task, chunk.text)
        if text_score >= 0.3:
            logger.debug(f"Chunk {chunk.chunk_id} matched by text overlap: {text_score:.3f}")
            return True

        return False

    def _match_rule_number(self, sub_task: str, rule_number: str) -> bool:
        """Check if sub-task explicitly mentions the rule number.

        Args:
            sub_task: The sub-task text
            rule_number: The rule number to match (e.g., "14A.35")

        Returns:
            True if rule number is mentioned in sub-task
        """
        # Extract all rule number patterns from sub-task
        rule_pattern = r'\b\d+[A-Z]?\.\d+[A-Z]?\b'
        task_rules = re.findall(rule_pattern, sub_task)

        # Direct match
        if rule_number in task_rules:
            return True

        # Fuzzy match: check if rule number appears in text (case-insensitive)
        if rule_number.lower() in sub_task.lower():
            return True

        return False

    def _match_section_title(self, sub_task: str, section_title: str) -> bool:
        task_lower = sub_task.lower()
        title_lower = section_title.lower()

        task_words = _tokenize_mixed(task_lower)
        title_words = _tokenize_mixed(title_lower)

        if not task_words or not title_words:
            return False

        overlap = task_words & title_words
        overlap_ratio = len(overlap) / min(len(task_words), len(title_words))

        if overlap_ratio >= 0.4:
            return True

        hkex_terms = {
            'disclosure', 'connected', 'transaction', 'notifiable',
            'acquisition', 'disposal', 'listing', 'requirement',
            'obligation', 'exemption', 'threshold', 'percentage'
        }

        task_hkex = task_words & hkex_terms
        title_hkex = title_words & hkex_terms

        if task_hkex and title_hkex and (task_hkex & title_hkex):
            return True

        return False

    def _text_overlap_score(self, sub_task: str, chunk_text: str) -> float:
        """Calculate text overlap score between sub-task and chunk text.

        Handles both English (space-tokenized) and Chinese (character bigrams).
        """
        task_lower = sub_task.lower()
        text_lower = chunk_text.lower()

        task_words = _tokenize_mixed(task_lower)
        text_words = _tokenize_mixed(text_lower)

        if not task_words:
            return 0.0

        overlap = task_words & text_words
        overlap_ratio = len(overlap) / len(task_words)

        key_terms = ['disclosure', 'obligation', 'requirement', 'threshold', 'rule', 'transaction']
        key_term_bonus = 0.0
        for term in key_terms:
            if term in task_lower and term in text_lower:
                key_term_bonus += 0.1

        key_term_bonus = min(key_term_bonus, 0.3)

        return min(overlap_ratio + key_term_bonus, 1.0)
