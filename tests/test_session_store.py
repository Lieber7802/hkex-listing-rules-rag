"""Tests for conversation models and SessionStore."""

import json
import time
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
import pytest

from app.models.conversation import ConversationTurn, ConversationSession


class TestConversationTurn:
    """Tests for ConversationTurn model."""

    def test_create_user_turn(self):
        turn = ConversationTurn(role="user", content="什么是关联交易?")
        assert turn.role == "user"
        assert turn.content == "什么是关联交易?"
        assert turn.timestamp is not None
        assert turn.metadata is None

    def test_create_assistant_turn_with_metadata(self):
        turn = ConversationTurn(
            role="assistant",
            content="关联交易是指...",
            metadata={"citations": ["Rule 14A.01"]},
        )
        assert turn.role == "assistant"
        assert turn.metadata == {"citations": ["Rule 14A.01"]}

    def test_serialization_round_trip(self):
        turn = ConversationTurn(role="user", content="test query")
        json_str = turn.model_dump_json()
        restored = ConversationTurn.model_validate_json(json_str)
        assert restored.role == turn.role
        assert restored.content == turn.content


class TestConversationSession:
    """Tests for ConversationSession model."""

    def test_create_empty_session(self):
        session = ConversationSession()
        assert session.conversation_id  # auto-generated UUID
        assert len(session.conversation_id) == 36  # UUID format
        assert session.turns == []
        assert session.turn_count == 0
        assert session.is_empty is True

    def test_turn_count_counts_user_only(self):
        session = ConversationSession(
            turns=[
                ConversationTurn(role="user", content="Q1"),
                ConversationTurn(role="assistant", content="A1"),
                ConversationTurn(role="user", content="Q2"),
                ConversationTurn(role="assistant", content="A2"),
            ]
        )
        assert session.turn_count == 2

    def test_get_recent_turns_within_window(self):
        turns = [
            ConversationTurn(role="user", content="Q1"),
            ConversationTurn(role="assistant", content="A1"),
        ]
        session = ConversationSession(turns=turns)
        recent = session.get_recent_turns(max_pairs=5)
        assert len(recent) == 2
        assert recent[0].content == "Q1"

    def test_get_recent_turns_exceeds_window(self):
        turns = []
        for i in range(12):  # 6 pairs
            role = "user" if i % 2 == 0 else "assistant"
            turns.append(ConversationTurn(role=role, content=f"msg{i}"))
        session = ConversationSession(turns=turns)

        recent = session.get_recent_turns(max_pairs=2)
        assert len(recent) == 4
        assert recent[0].content == "msg8"  # last 4 items
        assert recent[-1].content == "msg11"

    def test_get_older_turns_returns_before_window(self):
        turns = []
        for i in range(12):  # 6 pairs
            role = "user" if i % 2 == 0 else "assistant"
            turns.append(ConversationTurn(role=role, content=f"msg{i}"))
        session = ConversationSession(turns=turns)

        older = session.get_older_turns(max_pairs=2)
        assert len(older) == 8  # 12 - 4 = 8
        assert older[0].content == "msg0"
        assert older[-1].content == "msg7"

    def test_get_older_turns_empty_when_fits_in_window(self):
        turns = [
            ConversationTurn(role="user", content="Q1"),
            ConversationTurn(role="assistant", content="A1"),
        ]
        session = ConversationSession(turns=turns)
        older = session.get_older_turns(max_pairs=5)
        assert older == []

    def test_is_empty(self):
        session = ConversationSession()
        assert session.is_empty is True
        session.turns.append(ConversationTurn(role="user", content="hi"))
        assert session.is_empty is False


class TestSessionStore:
    """Tests for SessionStore service."""

    @pytest.fixture
    def store(self, tmp_path):
        """Create a fresh SessionStore with temp storage."""
        from app.services.session_store import SessionStore

        return SessionStore(storage_path=tmp_path, ttl_minutes=60, max_turns=50)

    def test_get_or_create_new_session(self, store):
        session = store.get_or_create(None)
        assert session.conversation_id
        assert session.is_empty

    def test_get_or_create_returns_same_session(self, store):
        session1 = store.get_or_create(None)
        session2 = store.get_or_create(session1.conversation_id)
        assert session1.conversation_id == session2.conversation_id

    def test_get_or_create_invalid_id_creates_new(self, store):
        session = store.get_or_create("nonexistent-id-12345")
        assert session.conversation_id != "nonexistent-id-12345"
        assert session.is_empty

    def test_append_turn(self, store):
        session = store.get_or_create(None)
        cid = session.conversation_id

        store.append_turn(cid, ConversationTurn(role="user", content="Q1"))
        store.append_turn(cid, ConversationTurn(role="assistant", content="A1"))

        updated = store.get_or_create(cid)
        assert updated.turn_count == 1
        assert len(updated.turns) == 2

    def test_get_history(self, store):
        session = store.get_or_create(None)
        cid = session.conversation_id

        for i in range(10):
            role = "user" if i % 2 == 0 else "assistant"
            store.append_turn(cid, ConversationTurn(role=role, content=f"msg{i}"))

        history = store.get_history(cid, max_turns=2)
        # max_turns=2 pairs = 4 messages
        assert len(history) == 4

    def test_expired_session_creates_new(self, tmp_path):
        from app.services.session_store import SessionStore

        store = SessionStore(storage_path=tmp_path, ttl_minutes=0, max_turns=50)
        session = store.get_or_create(None)
        cid = session.conversation_id

        # TTL=0 means never expire — manually force expiry by changing last_active
        store._sessions[cid].last_active = datetime.now(tz=timezone.utc) - timedelta(days=1)
        store._ttl = timedelta(minutes=60)  # Override TTL check

        new_session = store.get_or_create(cid)
        assert new_session.conversation_id != cid

    def test_cleanup_expired(self, tmp_path):
        from app.services.session_store import SessionStore

        store = SessionStore(storage_path=tmp_path, ttl_minutes=0, max_turns=50)
        s1 = store.get_or_create(None)
        s2 = store.get_or_create(None)

        # Force expire both by overriding last_active and TTL
        store._sessions[s1.conversation_id].last_active = datetime.now(tz=timezone.utc) - timedelta(days=1)
        store._sessions[s2.conversation_id].last_active = datetime.now(tz=timezone.utc) - timedelta(days=1)
        store._ttl = timedelta(minutes=60)

        removed = store.cleanup_expired()
        assert removed == 2
        assert len(store._sessions) == 0

    def test_jsonl_persistence_write(self, store, tmp_path):
        session = store.get_or_create(None)
        cid = session.conversation_id

        store.append_turn(cid, ConversationTurn(role="user", content="hello"))

        filepath = tmp_path / f"{cid}.jsonl"
        assert filepath.exists()
        lines = filepath.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["role"] == "user"
        assert data["content"] == "hello"

    def test_jsonl_persistence_load(self, tmp_path):
        from app.services.session_store import SessionStore

        # Pre-write a JSONL file with recent timestamps
        cid = "test-session-123"
        filepath = tmp_path / f"{cid}.jsonl"
        now = datetime.now(tz=timezone.utc).isoformat()
        turns = [
            {"role": "user", "content": "Q1", "timestamp": now},
            {"role": "assistant", "content": "A1", "timestamp": now},
        ]
        with open(filepath, "w", encoding="utf-8") as f:
            for t in turns:
                f.write(json.dumps(t) + "\n")

        store = SessionStore(storage_path=tmp_path, ttl_minutes=60, max_turns=50)
        session = store.get_or_create(cid)
        assert session.conversation_id == cid
        assert len(session.turns) == 2
        assert session.turns[0].content == "Q1"

    def test_lazy_load_only_loads_requested_session(self, tmp_path):
        from app.services.session_store import SessionStore

        session_a_id = "session-a"
        session_b_id = "session-b"

        file_a = tmp_path / f"{session_a_id}.jsonl"
        file_b = tmp_path / f"{session_b_id}.jsonl"

        turn_a = ConversationTurn(role="user", content="hello A")
        turn_b = ConversationTurn(role="user", content="hello B")

        file_a.write_text(turn_a.model_dump_json() + "\n", encoding="utf-8")
        file_b.write_text(turn_b.model_dump_json() + "\n", encoding="utf-8")

        store = SessionStore(storage_path=tmp_path)
        assert len(store._sessions) == 0  # no eager loading

        session = store.get_or_create(session_a_id)
        assert session.conversation_id == session_a_id
        assert len(session.turns) == 1
        assert session.turns[0].content == "hello A"
        assert len(store._sessions) == 1

        # session-b should still not be loaded
        assert session_b_id not in store._sessions

    def test_thread_safety_concurrent_append(self, store):
        session = store.get_or_create(None)
        cid = session.conversation_id

        def append_turns(start):
            for i in range(10):
                store.append_turn(
                    cid, ConversationTurn(role="user", content=f"t{start}_{i}")
                )

        threads = [threading.Thread(target=append_turns, args=(n,)) for n in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        session = store.get_or_create(cid)
        assert len(session.turns) == 50  # 5 threads * 10 turns

    def test_max_turns_limit(self, tmp_path):
        from app.services.session_store import SessionStore

        store = SessionStore(storage_path=tmp_path, ttl_minutes=60, max_turns=4)
        session = store.get_or_create(None)
        cid = session.conversation_id

        for i in range(6):
            store.append_turn(cid, ConversationTurn(role="user", content=f"msg{i}"))

        session = store.get_or_create(cid)
        assert len(session.turns) <= 4
        # Most recent messages preserved
        assert session.turns[-1].content == "msg5"
