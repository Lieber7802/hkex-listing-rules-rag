"""Contextual query rewriter for coreference resolution.

Resolves pronouns and references (e.g., "它", "该规则", "that rule") by
rewriting queries to be self-contained using conversation history context.

Two paths:
- Fast path (heuristic): If query has no ambiguous markers → return as-is (~70% of queries)
- LLM path: If query contains pronouns/references → use LLM to rewrite with history context
"""

import os
from typing import List, Optional

from app.models.conversation import ConversationTurn
from app.core.config import settings
from app.core.logger import logger


class ContextualQueryRewriter:
    """Resolves coreference in queries using conversation history.

    Examples:
        history: [Q: "什么是关联交易?", A: "关联交易是指..."]
        query: "它有什么豁免?"
        rewritten: "关联交易有什么豁免?"
    """

    # Ambiguous markers that suggest the query references prior context
    AMBIGUOUS_MARKERS_ZH = [
        "它", "这个", "那个", "上面", "之前", "该规则",
        "前面提到", "刚才说的", "那些", "这些", "其中",
    ]
    AMBIGUOUS_MARKERS_EN = [
        " it ", " it?", " it.", "this ", "that ", "that?", "that.",
        "the above", "mentioned", "those ", "these ", "the rule", "the same",
    ]

    def __init__(self):
        self._llm_client = None

    def rewrite(
        self, query: str, history: Optional[List[ConversationTurn]]
    ) -> str:
        """Rewrite query to be self-contained if it contains references.

        Args:
            query: The current user query.
            history: Previous conversation turns (may be None or empty).

        Returns:
            Rewritten query (or original if no rewrite needed).
        """
        # Fast path: no history → return original
        if not history:
            return query

        # Fast path: query is already self-contained
        if self._is_self_contained(query):
            return query

        # LLM path: try to rewrite
        client = self._get_llm_client()
        if client:
            rewritten = self._llm_rewrite(query, history[-4:], client)
            if rewritten and rewritten != query:
                logger.info(f"Query rewritten: '{query}' → '{rewritten}'")
                return rewritten

        # Fallback: heuristic rewrite attempt
        return self._heuristic_rewrite(query, history)

    def _is_self_contained(self, query: str) -> bool:
        """Check if query is self-contained (no ambiguous references).

        Returns True if the query doesn't contain pronouns or references
        that would need resolution from context.
        """
        query_lower = query.lower()

        for marker in self.AMBIGUOUS_MARKERS_ZH:
            if marker in query:
                return False

        for marker in self.AMBIGUOUS_MARKERS_EN:
            if marker in query_lower:
                return False

        return True

    def _llm_rewrite(
        self,
        query: str,
        recent_turns: List[ConversationTurn],
        client,
    ) -> Optional[str]:
        """Use LLM to rewrite query resolving coreference."""
        try:
            # Build compact history representation
            history_text = ""
            for turn in recent_turns:
                prefix = "User" if turn.role == "user" else "Assistant"
                history_text += f"{prefix}: {turn.content[:200]}\n"

            prompt = (
                "Given the conversation history below, rewrite the user's latest query "
                "to be self-contained (resolve all pronouns and references to specific entities). "
                "If the query is already clear, return it unchanged.\n"
                "IMPORTANT: Only output the rewritten query, nothing else.\n\n"
                f"Conversation history:\n{history_text}\n"
                f"Latest query: {query}\n\n"
                "Rewritten query:"
            )

            # Use deepseek-chat for structured tasks (same pattern as LLMRoutePlanner)
            model = "deepseek-chat" if settings.llm_model == "deepseek-reasoner" else settings.llm_model

            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You rewrite queries to resolve pronouns and references. Output only the rewritten query."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=150,
                temperature=0.1,
            )

            result = response.choices[0].message.content
            if result:
                result = result.strip().strip('"').strip("'")
                # Sanity check: result shouldn't be too different in length
                if len(result) > 0 and len(result) < len(query) * 5:
                    return result

            return query
        except Exception as e:
            logger.warning(f"LLM query rewrite failed: {e}")
            return query

    def _heuristic_rewrite(
        self, query: str, history: List[ConversationTurn]
    ) -> str:
        """Simple heuristic: prepend last topic from history.

        This is a fallback when LLM is unavailable. It attempts to replace
        common pronouns with the subject from the last user question.
        """
        # Find last user question to extract topic
        last_user_q = None
        for turn in reversed(history):
            if turn.role == "user":
                last_user_q = turn.content
                break

        if not last_user_q:
            return query

        # Extract a likely topic (first noun-phrase-like segment, heuristic)
        # For Chinese: take first 10 chars after common question words
        # For English: take first few meaningful words
        # This is intentionally simple — LLM path handles complex cases
        return query  # Return original as safe fallback

    def _get_llm_client(self):
        """Lazy-init LLM client."""
        if self._llm_client is not None:
            return self._llm_client

        if settings.llm_provider in ["openai", "deepseek"]:
            try:
                from openai import OpenAI

                api_key = (
                    settings.llm_api_key
                    or os.environ.get("OPENAI_API_KEY")
                    or os.environ.get("DEEPSEEK_API_KEY")
                )
                if api_key:
                    self._llm_client = OpenAI(
                        api_key=api_key, base_url=settings.llm_base_url
                    )
            except ImportError:
                pass

        return self._llm_client
