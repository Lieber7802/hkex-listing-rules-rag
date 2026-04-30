import re
from typing import List

from app.core.logger import logger


class QueryRewriter:
    """Rewrites queries for targeted second retrieval based on coverage gaps.

    Uses heuristic keyword extraction — no LLM dependency.
    """

    MAX_REWRITTEN_QUERIES = 3

    def __init__(self):
        self.rule_pattern = re.compile(
            r'\b(?:Rule\s+)?(\d+[A-Z]?\.\d+[A-Z]?)\b', re.IGNORECASE
        )

    def rewrite(
        self,
        original_query: str,
        missing_information: List[str],
    ) -> List[str]:
        """Generate targeted queries from missing coverage information.

        Args:
            original_query: The user's original query
            missing_information: Sub-tasks that weren't covered by first retrieval

        Returns:
            List of rewritten queries (max 3), or [original_query] if nothing missing
        """
        if not missing_information:
            return [original_query]

        rewritten: List[str] = []
        seen: set = set()

        for subtask in missing_information[: self.MAX_REWRITTEN_QUERIES]:
            query = self._rewrite_subtask(subtask, original_query)
            normalized = query.lower().strip()
            if normalized not in seen:
                seen.add(normalized)
                rewritten.append(query)

        if not rewritten:
            return [original_query]

        logger.info(
            f"QueryRewriter: rewrote {len(rewritten)} targeted queries "
            f"from {len(missing_information)} gaps"
        )
        return rewritten

    def _rewrite_subtask(self, subtask: str, original_query: str) -> str:
        """Turn a missing subtask into a focused retrieval query.

        Strategy:
        1. If subtask contains rule numbers, make a rule-focused query
        2. Otherwise, use the subtask text directly (it's already a natural language fragment)
        """
        rule_matches = self.rule_pattern.findall(subtask)

        if rule_matches:
            # Build a rule-focused query
            rules_str = " and ".join(f"Rule {r}" for r in rule_matches)
            # Strip the rule references from the subtask to get the topic
            topic = self.rule_pattern.sub("", subtask).strip()
            topic = re.sub(r'\s+', ' ', topic).strip(" ,;-")

            if topic:
                return f"{topic} under {rules_str}"
            else:
                return f"HKEX Listing Rules {rules_str}"

        # No rule numbers — use the subtask directly
        return subtask
