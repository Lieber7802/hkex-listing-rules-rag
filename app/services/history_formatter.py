"""History formatting service for multi-turn conversation.

Converts conversation history into formats suitable for LLM injection:
- Sliding window (recent N pairs as messages[])
- Summary generation for older turns beyond the window
"""

from typing import Dict, List, Optional, Tuple

from app.models.conversation import ConversationTurn
from app.core.config import settings
from app.core.llm_client import get_llm_client
from app.core.logger import logger


class HistoryFormatter:
    """Formats conversation history for LLM context injection.

    Strategy:
    - Recent turns (within window): passed as structured messages[]
    - Older turns (beyond window): summarized into a single sentence
    """

    def __init__(self):
        pass

    def format_as_messages(
        self, turns: List[ConversationTurn], max_turns: int = 5
    ) -> List[Dict[str, str]]:
        """Format recent turns as LLM message list.

        Args:
            turns: Full list of conversation turns.
            max_turns: Maximum number of Q&A pairs to include.

        Returns:
            List of {"role": ..., "content": ...} dicts.
        """
        if not turns:
            return []

        # Take last N pairs (2 * max_turns messages)
        max_items = max_turns * 2
        recent = turns[-max_items:] if len(turns) > max_items else turns

        return [{"role": t.role, "content": t.content} for t in recent]

    def format_for_reasoning(
        self, turns: List[ConversationTurn], max_turns: int = 5
    ) -> Tuple[List[Dict[str, str]], Optional[str]]:
        """Format history for the reasoning agent.

        Returns:
            Tuple of (recent_messages, optional_summary_of_older_turns)
        """
        if not turns:
            return [], None

        max_items = max_turns * 2

        if len(turns) <= max_items:
            # All fits in window
            messages = [{"role": t.role, "content": t.content} for t in turns]
            return messages, None

        # Split into older + recent
        older_turns = turns[:-max_items]
        recent_turns = turns[-max_items:]

        messages = [{"role": t.role, "content": t.content} for t in recent_turns]
        summary = self.generate_summary(older_turns)

        return messages, summary

    def generate_summary(
        self, older_turns: List[ConversationTurn]
    ) -> Optional[str]:
        """Generate a brief summary of older conversation turns.

        Uses LLM if available, otherwise falls back to a simple concatenation
        of the user's questions.

        Args:
            older_turns: Turns that are beyond the recent window.

        Returns:
            A 1-2 sentence summary, or None if no turns provided.
        """
        if not older_turns:
            return None

        # Try LLM-based summary
        client = get_llm_client()
        if client:
            return self._llm_summarize(older_turns, client)

        # Fallback: concatenate user questions
        return self._fallback_summarize(older_turns)

    def _fallback_summarize(self, turns: List[ConversationTurn]) -> str:
        """Simple fallback: list the user's previous questions."""
        user_questions = [t.content for t in turns if t.role == "user"]
        if not user_questions:
            return ""

        # Take at most 3 questions for brevity
        sampled = user_questions[-3:]
        topics = "; ".join(q[:50] for q in sampled)
        return f"Earlier questions covered: {topics}"

    def _llm_summarize(self, turns: List[ConversationTurn], client) -> Optional[str]:
        """Use LLM to generate a concise summary of older turns."""
        try:
            # Build a compact representation
            lines = []
            for t in turns[-6:]:  # at most last 3 pairs from older
                prefix = "Q" if t.role == "user" else "A"
                lines.append(f"{prefix}: {t.content[:100]}")

            prompt = (
                "Summarize the following earlier conversation in 1-2 sentences. "
                "Focus on the main topics discussed:\n\n"
                + "\n".join(lines)
            )

            response = client.chat.completions.create(
                model=settings.llm_model,
                messages=[
                    {"role": "system", "content": "Summarize conversations concisely."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=100,
                temperature=0.3,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.warning(f"LLM summary generation failed: {e}")
            return self._fallback_summarize(turns)
