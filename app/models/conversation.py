"""Conversation data models for multi-turn dialog support."""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
import uuid


class ConversationTurn(BaseModel):
    """A single turn in a conversation (user query or assistant response)."""

    role: str = Field(..., description="Role: 'user' or 'assistant'")
    content: str = Field(..., description="Message content (query or answer)")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional metadata (citations, tool_calls for assistant turns)",
    )


class ConversationSession(BaseModel):
    """A multi-turn conversation session."""

    conversation_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique session identifier",
    )
    turns: List[ConversationTurn] = Field(
        default_factory=list, description="Ordered list of conversation turns"
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    last_active: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Session-level metadata (e.g., dominant_topic)",
    )

    @property
    def turn_count(self) -> int:
        """Number of user turns (question count)."""
        return len([t for t in self.turns if t.role == "user"])

    @property
    def is_empty(self) -> bool:
        """Whether the session has any turns."""
        return len(self.turns) == 0

    def get_recent_turns(self, max_pairs: int = 5) -> List[ConversationTurn]:
        """Get most recent N pairs of turns (user+assistant).

        Args:
            max_pairs: Maximum number of Q&A pairs to return.

        Returns:
            List of turns, ordered chronologically. At most 2*max_pairs items.
        """
        max_items = max_pairs * 2
        if len(self.turns) <= max_items:
            return list(self.turns)
        return list(self.turns[-max_items:])

    def get_older_turns(self, max_pairs: int = 5) -> List[ConversationTurn]:
        """Get turns older than the recent window (for summarization).

        Args:
            max_pairs: The window size used for recent turns.

        Returns:
            List of older turns, or empty if all fit in window.
        """
        max_items = max_pairs * 2
        if len(self.turns) <= max_items:
            return []
        return list(self.turns[:-max_items])
