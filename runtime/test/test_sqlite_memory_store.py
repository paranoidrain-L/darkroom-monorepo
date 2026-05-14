# -*- coding: utf-8 -*-
"""Intended behavior tests for SQLiteMemoryStore."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from runtime.memory import ConversationTurn, MemoryScope, MemoryStore, TurnStatus

sqlite_store_module = pytest.importorskip(
    "runtime.memory.sqlite_store",
    reason="SQLiteMemoryStore API is not implemented yet",
)
SQLiteMemoryStore = sqlite_store_module.SQLiteMemoryStore


def make_store(db_path: Path) -> MemoryStore:
    return SQLiteMemoryStore(str(db_path))


def make_scope(
    *,
    user_id: str = "ou_user_1",
    conversation_id: str = "oc_chat_1",
    thread_id: str = "thread_1",
) -> MemoryScope:
    return MemoryScope(
        app="feishu_bot",
        channel="feishu",
        user_id=user_id,
        conversation_id=conversation_id,
        thread_id=thread_id,
        metadata={"chat_type": "p2p"},
    )


def user_turn(
    scope: MemoryScope,
    *,
    turn_id: str,
    content: str = "user question",
    source_message_id: str = "message_1",
    status: TurnStatus = TurnStatus.ACCEPTED,
) -> ConversationTurn:
    return ConversationTurn(
        turn_id=turn_id,
        scope=scope,
        role="user",
        content=content,
        status=status,
        source_message_id=source_message_id,
    )


def assistant_turn(
    scope: MemoryScope,
    *,
    turn_id: str,
    content: str = "assistant answer",
    request_message_id: str = "message_1",
    parent_turn_id: str = "user_1",
    status: TurnStatus = TurnStatus.DELIVERED,
) -> ConversationTurn:
    return ConversationTurn(
        turn_id=turn_id,
        scope=scope,
        role="assistant",
        content=content,
        status=status,
        parent_turn_id=parent_turn_id,
        request_message_id=request_message_id,
    )


def set_summary(store: MemoryStore, scope: MemoryScope, summary: str) -> None:
    setter = getattr(store, "set_summary", None)
    assert setter is not None, "SQLiteMemoryStore must expose set_summary(scope, summary)"
    setter(scope, summary)


def add_fact(store: MemoryStore, scope: MemoryScope, fact: str) -> None:
    adder = getattr(store, "add_fact", None)
    assert adder is not None, "SQLiteMemoryStore must expose add_fact(scope, fact)"
    adder(scope, fact)


def test_bootstrap_and_reopen_persist_turns(tmp_path: Path) -> None:
    db_path = tmp_path / "memory.sqlite3"
    scope = make_scope()
    store = make_store(db_path)

    created = store.append_user_turn(
        user_turn(scope, turn_id="user_1", content="first question", source_message_id="msg_1")
    )
    store.append_assistant_turn(
        assistant_turn(
            scope,
            turn_id="assistant_1",
            content="first answer",
            parent_turn_id=created.user_turn.turn_id or "",
            request_message_id="msg_1",
        )
    )

    reopened = make_store(db_path)
    recent = list(reopened.get_recent_turns(scope, limit=10))

    assert db_path.exists()
    assert [(turn.turn_id, turn.role, turn.content) for turn in recent] == [
        ("user_1", "user", "first question"),
        ("assistant_1", "assistant", "first answer"),
    ]


def test_bootstrap_creates_trial_tables_and_wal_journal(tmp_path: Path) -> None:
    db_path = tmp_path / "memory.sqlite3"
    store = SQLiteMemoryStore(str(db_path))
    store.close()

    with sqlite3.connect(db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]

    assert {"conversation_turns", "conversation_summaries", "memory_facts"} <= tables
    assert journal_mode == "wal"


def test_scope_isolation_for_turns_and_source_message_id(tmp_path: Path) -> None:
    store = make_store(tmp_path / "memory.sqlite3")
    scope_a = make_scope(thread_id="thread_a")
    scope_b = make_scope(thread_id="thread_b")

    result_a = store.append_user_turn(
        user_turn(scope_a, turn_id="user_a", content="question a", source_message_id="same_msg")
    )
    result_b = store.append_user_turn(
        user_turn(scope_b, turn_id="user_b", content="question b", source_message_id="same_msg")
    )
    store.append_assistant_turn(
        assistant_turn(scope_a, turn_id="assistant_a", content="answer a")
    )

    assert result_a.created is True
    assert result_b.created is True
    assert [turn.content for turn in store.get_recent_turns(scope_a, limit=10)] == [
        "question a",
        "answer a",
    ]
    assert [turn.content for turn in store.get_recent_turns(scope_b, limit=10)] == ["question b"]


def test_source_message_id_idempotency_returns_delivered_assistant(
    tmp_path: Path,
) -> None:
    store = make_store(tmp_path / "memory.sqlite3")
    scope = make_scope()

    original = store.append_user_turn(
        user_turn(scope, turn_id="user_1", content="original", source_message_id="msg_1")
    )
    store.append_assistant_turn(
        assistant_turn(
            scope,
            turn_id="assistant_answered",
            content="not delivered yet",
            parent_turn_id=original.user_turn.turn_id or "",
            request_message_id="msg_1",
            status=TurnStatus.ANSWERED,
        )
    )
    store.append_assistant_turn(
        assistant_turn(
            scope,
            turn_id="assistant_delivered",
            content="already delivered",
            parent_turn_id=original.user_turn.turn_id or "",
            request_message_id="msg_1",
            status=TurnStatus.DELIVERED,
        )
    )

    duplicate = store.append_user_turn(
        user_turn(scope, turn_id="user_duplicate", content="duplicate", source_message_id="msg_1")
    )

    assert duplicate.created is False
    assert duplicate.user_turn.turn_id == "user_1"
    assert duplicate.should_generate is False
    assert duplicate.has_delivered_response is True
    assert duplicate.existing_assistant_turn is not None
    assert duplicate.existing_assistant_turn.turn_id == "assistant_delivered"
    assert duplicate.existing_assistant_turn.content == "already delivered"
    assert len([turn for turn in store.get_recent_turns(scope, limit=10) if turn.role == "user"]) == 1


def test_recent_turns_exclude_non_delivered_assistant_turns(tmp_path: Path) -> None:
    store = make_store(tmp_path / "memory.sqlite3")
    scope = make_scope()

    store.append_user_turn(user_turn(scope, turn_id="user_1", source_message_id="msg_1"))
    store.append_assistant_turn(
        assistant_turn(scope, turn_id="assistant_answered", status=TurnStatus.ANSWERED)
    )
    store.append_assistant_turn(
        assistant_turn(scope, turn_id="assistant_failed", status=TurnStatus.FAILED)
    )
    store.append_assistant_turn(
        assistant_turn(scope, turn_id="assistant_unknown", status=TurnStatus.UNKNOWN)
    )
    store.append_assistant_turn(
        assistant_turn(scope, turn_id="assistant_delivered", status=TurnStatus.DELIVERED)
    )

    recent = list(store.get_recent_turns(scope, limit=10))

    assert [(turn.turn_id, turn.status) for turn in recent] == [
        ("user_1", TurnStatus.ACCEPTED),
        ("assistant_delivered", TurnStatus.DELIVERED),
    ]


def test_update_turn_status_controls_recent_turn_eligibility(tmp_path: Path) -> None:
    store = make_store(tmp_path / "memory.sqlite3")
    scope = make_scope()

    store.append_user_turn(user_turn(scope, turn_id="user_1", source_message_id="msg_1"))
    store.append_assistant_turn(
        assistant_turn(scope, turn_id="assistant_1", status=TurnStatus.ANSWERED)
    )

    assert [turn.turn_id for turn in store.get_recent_turns(scope, limit=10)] == ["user_1"]

    store.update_turn_status("assistant_1", TurnStatus.DELIVERED)
    assert [turn.turn_id for turn in store.get_recent_turns(scope, limit=10)] == [
        "user_1",
        "assistant_1",
    ]

    store.update_turn_status("assistant_1", TurnStatus.FAILED)
    assert [turn.turn_id for turn in store.get_recent_turns(scope, limit=10)] == ["user_1"]


def test_summary_and_facts_persist_and_respect_scope_and_limit(tmp_path: Path) -> None:
    db_path = tmp_path / "memory.sqlite3"
    scope_a = make_scope(thread_id="thread_a")
    scope_b = make_scope(thread_id="thread_b")
    store = make_store(db_path)

    set_summary(store, scope_a, "summary a")
    add_fact(store, scope_a, "fact a1")
    add_fact(store, scope_a, "fact a2")
    add_fact(store, scope_b, "fact b1")

    reopened = make_store(db_path)

    assert reopened.get_summary(scope_a) == "summary a"
    assert reopened.get_summary(scope_b) == ""
    assert list(reopened.get_facts(scope_a, limit=1)) == ["fact a1"]
    assert list(reopened.get_facts(scope_a, limit=10)) == ["fact a1", "fact a2"]
    assert list(reopened.get_facts(scope_b, limit=10)) == ["fact b1"]


def test_clear_scope_removes_only_that_scope(tmp_path: Path) -> None:
    store = make_store(tmp_path / "memory.sqlite3")
    scope_a = make_scope(thread_id="thread_a")
    scope_b = make_scope(thread_id="thread_b")

    store.append_user_turn(user_turn(scope_a, turn_id="user_a", source_message_id="msg_a"))
    store.append_user_turn(user_turn(scope_b, turn_id="user_b", source_message_id="msg_b"))
    set_summary(store, scope_a, "summary a")
    set_summary(store, scope_b, "summary b")
    add_fact(store, scope_a, "fact a")
    add_fact(store, scope_b, "fact b")

    store.clear_scope(scope_a)

    assert list(store.get_recent_turns(scope_a, limit=10)) == []
    assert store.get_summary(scope_a) == ""
    assert list(store.get_facts(scope_a, limit=10)) == []
    assert [turn.turn_id for turn in store.get_recent_turns(scope_b, limit=10)] == ["user_b"]
    assert store.get_summary(scope_b) == "summary b"
    assert list(store.get_facts(scope_b, limit=10)) == ["fact b"]


def test_cleanup_retention_removes_only_expired_rows(tmp_path: Path) -> None:
    store = make_store(tmp_path / "memory.sqlite3")
    old_scope = make_scope(thread_id="old")
    fresh_scope = make_scope(thread_id="fresh")
    old_time = datetime.utcnow() - timedelta(days=10)

    store.append_user_turn(
        user_turn(old_scope, turn_id="old_user", source_message_id="old_msg", content="old")
    )
    store.append_assistant_turn(
        assistant_turn(
            old_scope,
            turn_id="old_assistant",
            request_message_id="old_msg",
            parent_turn_id="old_user",
            content="old answer",
        )
    )
    store.append_user_turn(
        user_turn(fresh_scope, turn_id="fresh_user", source_message_id="fresh_msg", content="fresh")
    )
    store.append_assistant_turn(
        assistant_turn(
            fresh_scope,
            turn_id="fresh_assistant",
            request_message_id="fresh_msg",
            parent_turn_id="fresh_user",
            content="fresh answer",
        )
    )
    set_summary(store, old_scope, "old summary")
    set_summary(store, fresh_scope, "fresh summary")
    add_fact(store, old_scope, "old fact")
    add_fact(store, fresh_scope, "fresh fact")

    with store._lock, store._conn:
        old_text = old_time.isoformat(timespec="microseconds")
        store._conn.execute("UPDATE conversation_turns SET created_at = ? WHERE thread_id = ?", (old_text, "old"))
        store._conn.execute(
            "UPDATE conversation_summaries SET updated_at = ? WHERE thread_id = ?",
            (old_text, "old"),
        )
        store._conn.execute(
            "UPDATE memory_facts SET created_at = ? WHERE thread_id = ?",
            (old_text, "old"),
        )

    counts = store.cleanup_retention(retention_days=7)

    assert counts == {
        "conversation_turns": 2,
        "conversation_summaries": 1,
        "memory_facts": 1,
    }
    assert list(store.get_recent_turns(old_scope, limit=10)) == []
    assert store.get_summary(old_scope) == ""
    assert list(store.get_facts(old_scope, limit=10)) == []
    assert [turn.turn_id for turn in store.get_recent_turns(fresh_scope, limit=10)] == [
        "fresh_user",
        "fresh_assistant",
    ]
    assert store.get_summary(fresh_scope) == "fresh summary"
    assert list(store.get_facts(fresh_scope, limit=10)) == ["fresh fact"]


def test_cleanup_retention_disabled_for_non_positive_days(tmp_path: Path) -> None:
    store = make_store(tmp_path / "memory.sqlite3")
    scope = make_scope()
    store.append_user_turn(user_turn(scope, turn_id="user_1", source_message_id="msg_1"))

    counts = store.cleanup_retention(retention_days=0)

    assert counts == {
        "conversation_turns": 0,
        "conversation_summaries": 0,
        "memory_facts": 0,
    }
    assert [turn.turn_id for turn in store.get_recent_turns(scope, limit=10)] == ["user_1"]
