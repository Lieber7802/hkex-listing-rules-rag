"""Thread-safe session store with in-memory cache and JSONL persistence.

Follows the project's singleton pattern (like IndexStore). Sessions are stored
in memory for fast access and persisted to JSONL files for durability.
"""

import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

from app.models.conversation import ConversationSession, ConversationTurn
from app.core.logger import logger


class SessionStore:
    """Thread-safe in-memory session store with JSONL file persistence.

    Each session is stored as a {conversation_id}.jsonl file containing
    one JSON object per line (one per turn). Sessions are loaded lazily:
    a session file is read from disk only when get_or_create(conversation_id)
    is called for a specific ID that is not already cached in memory.
    """

    def __init__(
        self,
        storage_path: Optional[Path] = None,
        ttl_minutes: int = 60,
        max_turns: int = 50,
    ):
        self._storage_path = Path(storage_path) if storage_path else Path("data/sessions")
        self._storage_path.mkdir(parents=True, exist_ok=True)
        self._ttl = timedelta(minutes=ttl_minutes)
        self._max_turns = max_turns
        self._sessions: Dict[str, ConversationSession] = {}
        self._lock = threading.Lock()

    def get_or_create(self, conversation_id: Optional[str] = None) -> ConversationSession:
        """Get existing session by ID or create a new one.

        If conversation_id is None or not found or expired, creates a new session.
        Sessions are lazy-loaded from disk on first access.
        Thread-safe.
        """
        with self._lock:
            if conversation_id and conversation_id in self._sessions:
                session = self._sessions[conversation_id]
                if self._is_expired(session):
                    logger.info(f"Session {conversation_id} expired, creating new")
                    del self._sessions[conversation_id]
                    return self._create_new()
                session.last_active = datetime.now(tz=timezone.utc)
                return session

            if conversation_id:
                session = self._load_session(conversation_id)
                if session is not None:
                    self._sessions[conversation_id] = session
                    return session
                logger.debug(f"Session {conversation_id} not found, creating new")

            return self._create_new()

    def append_turn(self, conversation_id: str, turn: ConversationTurn) -> None:
        """Append a turn to an existing session. Thread-safe.

        Also flushes the turn to the JSONL file and enforces max_turns limit.
        """
        with self._lock:
            session = self._sessions.get(conversation_id)
            if session is None:
                logger.warning(f"append_turn: session {conversation_id} not found")
                return

            session.turns.append(turn)
            session.last_active = datetime.now(tz=timezone.utc)

            # Enforce max_turns limit (keep most recent)
            if len(session.turns) > self._max_turns:
                session.turns = session.turns[-self._max_turns:]

            # Persist to disk
            self._flush_turn(conversation_id, turn)

    def get_history(
        self, conversation_id: str, max_turns: int = 5
    ) -> List[ConversationTurn]:
        """Get recent conversation history for a session.

        Args:
            conversation_id: Session to retrieve history for.
            max_turns: Maximum number of Q&A pairs to return.

        Returns:
            List of recent turns (at most 2*max_turns items).
        """
        with self._lock:
            session = self._sessions.get(conversation_id)
            if session is None:
                return []
            return session.get_recent_turns(max_pairs=max_turns)

    def cleanup_expired(self) -> int:
        """Remove all expired sessions. Returns count of removed sessions."""
        with self._lock:
            now = datetime.now(tz=timezone.utc)
            expired_ids = [
                sid
                for sid, session in self._sessions.items()
                if (now - session.last_active) > self._ttl
            ]
            for sid in expired_ids:
                del self._sessions[sid]
                filepath = self._session_path(sid)
                if filepath.exists():
                    try:
                        filepath.unlink()
                    except OSError:
                        pass
            if expired_ids:
                logger.info(f"Cleaned up {len(expired_ids)} expired sessions")
            return len(expired_ids)

    @property
    def session_count(self) -> int:
        """Number of active sessions."""
        with self._lock:
            return len(self._sessions)

    def _create_new(self) -> ConversationSession:
        """Create and register a new session. Must be called under lock."""
        session = ConversationSession()
        self._sessions[session.conversation_id] = session
        logger.debug(f"Created new session: {session.conversation_id}")
        return session

    def _is_expired(self, session: ConversationSession) -> bool:
        if self._ttl.total_seconds() == 0:
            return False  # TTL=0 means never expire
        return (datetime.now(tz=timezone.utc) - session.last_active) > self._ttl

    def _flush_turn(self, conversation_id: str, turn: ConversationTurn) -> None:
        """Append a single turn to the session's JSONL file."""
        try:
            filepath = self._session_path(conversation_id)
            with open(filepath, "a", encoding="utf-8") as f:
                f.write(turn.model_dump_json() + "\n")
        except OSError as e:
            logger.error(f"Failed to flush turn to disk: {e}")

    def _load_session(self, conversation_id: str) -> Optional[ConversationSession]:
        """Load a single session from disk if its JSONL file exists.

        Must be called under self._lock.
        """
        filepath = self._session_path(conversation_id)
        if not filepath.exists():
            return None

        session = self._load_session_file(filepath, conversation_id)
        if session is None:
            return None

        if self._is_expired(session):
            logger.info(f"Loaded session {conversation_id} is expired")
            return None

        session.last_active = datetime.now(tz=timezone.utc)
        return session

    def _session_path(self, conversation_id: str) -> Path:
        """Return a contained JSONL path or reject traversal before filesystem use."""
        if not conversation_id or Path(conversation_id).name != conversation_id:
            raise ValueError("invalid conversation_id")
        root = self._storage_path.resolve()
        candidate = (root / f"{conversation_id}.jsonl").resolve()
        if candidate.parent != root:
            raise ValueError("invalid conversation_id")
        return candidate

    def _load_from_disk(self) -> None:
        """(Legacy/debug) Load all sessions from disk into memory.

        Not called during normal initialization; sessions are lazy-loaded.
        """
        if not self._storage_path.exists():
            return

        loaded = 0
        for filepath in self._storage_path.glob("*.jsonl"):
            if filepath.suffix == ".expired":
                continue
            conversation_id = filepath.stem
            try:
                session = self._load_session_file(filepath, conversation_id)
                if session and not self._is_expired(session):
                    self._sessions[conversation_id] = session
                    loaded += 1
            except Exception as e:
                logger.warning(f"Failed to load session {conversation_id}: {e}")

        if loaded:
            logger.info(f"Loaded {loaded} active sessions from disk")

    def _load_session_file(
        self, filepath: Path, conversation_id: str
    ) -> Optional[ConversationSession]:
        """Load a single session from its JSONL file."""
        turns: List[ConversationTurn] = []

        with open(filepath, "r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    turn = ConversationTurn.model_validate_json(line)
                    turns.append(turn)
                except Exception as e:
                    logger.warning(
                        f"Skipping corrupted line {line_no} in {filepath.name}: {e}"
                    )

        if not turns:
            return None

        # Reconstruct session
        session = ConversationSession(
            conversation_id=conversation_id,
            turns=turns,
            created_at=turns[0].timestamp,
            last_active=turns[-1].timestamp,
        )
        return session
