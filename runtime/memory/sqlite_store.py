# -*- coding: utf-8 -*-
"""SQLite-backed MemoryStore implementation."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Sequence
from uuid import uuid4

from runtime.memory.types import ConversationTurn, IdempotencyResult, MemoryScope, TurnStatus


class SQLiteMemoryStore:
    """Persistent MemoryStore backed by a self-bootstrapped SQLite database."""

    def __init__(self, db_path: str | Path, *, busy_timeout_ms: int = 5000) -> None:
        self.db_path = str(db_path)
        self.busy_timeout_ms = busy_timeout_ms
        self._lock = RLock()
        self._conn = self._connect()
        self._bootstrap()

    def append_user_turn(self, turn: ConversationTurn) -> IdempotencyResult:
        self._ensure_turn_id(turn)
        with self._lock:
            if turn.source_message_id is not None:
                existing = self._get_user_turn_by_source_id(turn.scope, turn.source_message_id)
                if existing is not None:
                    return self._duplicate_result(existing)

            try:
                self._insert_turn(turn)
            except sqlite3.IntegrityError:
                if turn.source_message_id is None:
                    raise
                existing = self._get_user_turn_by_source_id(turn.scope, turn.source_message_id)
                if existing is None:
                    raise
                return self._duplicate_result(existing)

            return IdempotencyResult(created=True, user_turn=turn)

    def append_assistant_turn(self, turn: ConversationTurn) -> ConversationTurn:
        self._ensure_turn_id(turn)
        with self._lock:
            self._insert_turn(turn)
        return turn

    def update_turn_status(self, turn_id: str, status: TurnStatus) -> None:
        with self._lock, self._conn:
            cursor = self._conn.execute(
                "UPDATE conversation_turns SET status = ? WHERE turn_id = ?",
                (status.value, turn_id),
            )
            if cursor.rowcount == 0:
                raise KeyError(f"turn not found: {turn_id}")

    def get_recent_turns(self, scope: MemoryScope, limit: int) -> Sequence[ConversationTurn]:
        if limit <= 0:
            return []

        with self._lock:
            rows = self._conn.execute(
                """
                SELECT *
                FROM conversation_turns
                WHERE app = ?
                  AND channel = ?
                  AND user_id = ?
                  AND conversation_id = ?
                  AND thread_id = ?
                  AND (
                    (role = 'user' AND status = ?)
                    OR (role = 'assistant' AND status = ?)
                  )
                ORDER BY id DESC
                LIMIT ?
                """,
                (
                    scope.app,
                    scope.channel,
                    scope.user_id,
                    scope.conversation_id,
                    scope.thread_id,
                    TurnStatus.ACCEPTED.value,
                    TurnStatus.DELIVERED.value,
                    limit,
                ),
            ).fetchall()
        return [self._row_to_turn(row) for row in reversed(rows)]

    def get_turns_for_summary(self, scope: MemoryScope, limit: int) -> Sequence[ConversationTurn]:
        if limit <= 0:
            return []

        with self._lock:
            rows = self._conn.execute(
                """
                SELECT *
                FROM conversation_turns
                WHERE app = ?
                  AND channel = ?
                  AND user_id = ?
                  AND conversation_id = ?
                  AND thread_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (*scope.key(), limit),
            ).fetchall()
        return [self._row_to_turn(row) for row in reversed(rows)]

    def get_turn_count(self, scope: MemoryScope) -> int:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT COUNT(*) AS turn_count
                FROM conversation_turns
                WHERE app = ?
                  AND channel = ?
                  AND user_id = ?
                  AND conversation_id = ?
                  AND thread_id = ?
                """,
                scope.key(),
            ).fetchone()
        return 0 if row is None else int(row["turn_count"])

    def get_summary(self, scope: MemoryScope) -> str:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT summary
                FROM conversation_summaries
                WHERE app = ?
                  AND channel = ?
                  AND user_id = ?
                  AND conversation_id = ?
                  AND thread_id = ?
                """,
                scope.key(),
            ).fetchone()
        return "" if row is None else str(row["summary"])

    def get_summary_turn_count(self, scope: MemoryScope) -> int:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT turn_count
                FROM conversation_summaries
                WHERE app = ?
                  AND channel = ?
                  AND user_id = ?
                  AND conversation_id = ?
                  AND thread_id = ?
                """,
                scope.key(),
            ).fetchone()
        return 0 if row is None else int(row["turn_count"])

    def set_summary(self, scope: MemoryScope, summary: str, *, turn_count: int | None = None) -> None:
        updated_at = _datetime_to_text(datetime.now(timezone.utc))
        stored_turn_count = self.get_turn_count(scope) if turn_count is None else turn_count
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO conversation_summaries (
                    app, channel, user_id, conversation_id, thread_id, summary, updated_at, turn_count
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(app, channel, user_id, conversation_id, thread_id)
                DO UPDATE SET
                    summary = excluded.summary,
                    updated_at = excluded.updated_at,
                    turn_count = excluded.turn_count
                """,
                (*scope.key(), summary, updated_at, stored_turn_count),
            )

    def get_facts(self, scope: MemoryScope, limit: int) -> Sequence[str]:
        if limit <= 0:
            return []

        with self._lock:
            rows = self._conn.execute(
                """
                SELECT fact
                FROM memory_facts
                WHERE app = ?
                  AND channel = ?
                  AND user_id = ?
                  AND conversation_id = ?
                  AND thread_id = ?
                ORDER BY id ASC
                LIMIT ?
                """,
                (*scope.key(), limit),
            ).fetchall()
        return [str(row["fact"]) for row in rows]

    def add_fact(self, scope: MemoryScope, fact: str, *, metadata: dict[str, Any] | None = None) -> None:
        created_at = _datetime_to_text(datetime.now(timezone.utc))
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO memory_facts (
                    app, channel, user_id, conversation_id, thread_id,
                    fact, created_at, metadata
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (*scope.key(), fact, created_at, _json_dumps(metadata or {})),
            )

    def clear_scope(self, scope: MemoryScope) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                DELETE FROM conversation_turns
                WHERE app = ?
                  AND channel = ?
                  AND user_id = ?
                  AND conversation_id = ?
                  AND thread_id = ?
                """,
                scope.key(),
            )
            self._conn.execute(
                """
                DELETE FROM conversation_summaries
                WHERE app = ?
                  AND channel = ?
                  AND user_id = ?
                  AND conversation_id = ?
                  AND thread_id = ?
                """,
                scope.key(),
            )
            self._conn.execute(
                """
                DELETE FROM memory_facts
                WHERE app = ?
                  AND channel = ?
                  AND user_id = ?
                  AND conversation_id = ?
                  AND thread_id = ?
                """,
                scope.key(),
            )

    def cleanup_retention(self, retention_days: int) -> dict[str, int]:
        """Delete turns, summaries, and facts older than the retention window."""
        if retention_days <= 0:
            return {
                "conversation_turns": 0,
                "conversation_summaries": 0,
                "memory_facts": 0,
            }

        cutoff = _datetime_to_text(datetime.now(timezone.utc) - timedelta(days=retention_days))
        with self._lock, self._conn:
            turns = self._conn.execute(
                "DELETE FROM conversation_turns WHERE created_at < ?",
                (cutoff,),
            ).rowcount
            summaries = self._conn.execute(
                "DELETE FROM conversation_summaries WHERE updated_at < ?",
                (cutoff,),
            ).rowcount
            facts = self._conn.execute(
                "DELETE FROM memory_facts WHERE created_at < ?",
                (cutoff,),
            ).rowcount

        return {
            "conversation_turns": max(turns, 0),
            "conversation_summaries": max(summaries, 0),
            "memory_facts": max(facts, 0),
        }

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def __enter__(self) -> "SQLiteMemoryStore":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def _connect(self) -> sqlite3.Connection:
        if self.db_path != ":memory:" and not self.db_path.startswith("file:"):
            Path(self.db_path).expanduser().parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(
            self.db_path,
            timeout=self.busy_timeout_ms / 1000,
            check_same_thread=False,
            uri=self.db_path.startswith("file:"),
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(f"PRAGMA busy_timeout = {int(self.busy_timeout_ms)}")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def _bootstrap(self) -> None:
        with self._lock, self._conn:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS conversation_turns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    turn_id TEXT UNIQUE,
                    app TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    conversation_id TEXT NOT NULL,
                    thread_id TEXT NOT NULL,
                    scope_metadata TEXT NOT NULL DEFAULT '{}',
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    status TEXT NOT NULL,
                    source_message_id TEXT,
                    parent_turn_id TEXT,
                    request_message_id TEXT,
                    created_at TEXT NOT NULL,
                    metadata TEXT NOT NULL DEFAULT '{}'
                );

                CREATE UNIQUE INDEX IF NOT EXISTS idx_conversation_turns_user_source
                ON conversation_turns (
                    app, channel, user_id, conversation_id, thread_id, source_message_id
                )
                WHERE role = 'user' AND source_message_id IS NOT NULL;

                CREATE INDEX IF NOT EXISTS idx_conversation_turns_scope_recent
                ON conversation_turns (
                    app, channel, user_id, conversation_id, thread_id, id
                );

                CREATE INDEX IF NOT EXISTS idx_conversation_turns_request_status
                ON conversation_turns (
                    app, channel, user_id, conversation_id, thread_id,
                    request_message_id, status, id
                );

                CREATE TABLE IF NOT EXISTS conversation_summaries (
                    app TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    conversation_id TEXT NOT NULL,
                    thread_id TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    turn_count INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (app, channel, user_id, conversation_id, thread_id)
                );

                CREATE TABLE IF NOT EXISTS memory_facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    app TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    conversation_id TEXT NOT NULL,
                    thread_id TEXT NOT NULL,
                    fact TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    metadata TEXT NOT NULL DEFAULT '{}'
                );

                CREATE INDEX IF NOT EXISTS idx_memory_facts_scope
                ON memory_facts (
                    app, channel, user_id, conversation_id, thread_id, id
                );
                """
            )
            columns = {
                str(row["name"])
                for row in self._conn.execute("PRAGMA table_info(conversation_summaries)").fetchall()
            }
            if "turn_count" not in columns:
                self._conn.execute(
                    "ALTER TABLE conversation_summaries ADD COLUMN turn_count INTEGER NOT NULL DEFAULT 0"
                )

    def _insert_turn(self, turn: ConversationTurn) -> None:
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO conversation_turns (
                    turn_id,
                    app,
                    channel,
                    user_id,
                    conversation_id,
                    thread_id,
                    scope_metadata,
                    role,
                    content,
                    status,
                    source_message_id,
                    parent_turn_id,
                    request_message_id,
                    created_at,
                    metadata
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    turn.turn_id,
                    turn.scope.app,
                    turn.scope.channel,
                    turn.scope.user_id,
                    turn.scope.conversation_id,
                    turn.scope.thread_id,
                    _json_dumps(turn.scope.metadata),
                    turn.role,
                    turn.content,
                    turn.status.value,
                    turn.source_message_id,
                    turn.parent_turn_id,
                    turn.request_message_id,
                    _datetime_to_text(turn.created_at),
                    _json_dumps(turn.metadata),
                ),
            )

    def _get_user_turn_by_source_id(
        self,
        scope: MemoryScope,
        source_message_id: str,
    ) -> ConversationTurn | None:
        row = self._conn.execute(
            """
            SELECT *
            FROM conversation_turns
            WHERE app = ?
              AND channel = ?
              AND user_id = ?
              AND conversation_id = ?
              AND thread_id = ?
              AND role = 'user'
              AND source_message_id = ?
            ORDER BY id ASC
            LIMIT 1
            """,
            (*scope.key(), source_message_id),
        ).fetchone()
        return None if row is None else self._row_to_turn(row)

    def _get_delivered_assistant_for_source_id(
        self,
        scope: MemoryScope,
        source_message_id: str,
    ) -> ConversationTurn | None:
        row = self._conn.execute(
            """
            SELECT *
            FROM conversation_turns
            WHERE app = ?
              AND channel = ?
              AND user_id = ?
              AND conversation_id = ?
              AND thread_id = ?
              AND role = 'assistant'
              AND request_message_id = ?
              AND status = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (*scope.key(), source_message_id, TurnStatus.DELIVERED.value),
        ).fetchone()
        return None if row is None else self._row_to_turn(row)

    def _duplicate_result(self, user_turn: ConversationTurn) -> IdempotencyResult:
        assert user_turn.source_message_id is not None
        existing_assistant = self._get_delivered_assistant_for_source_id(
            user_turn.scope,
            user_turn.source_message_id,
        )
        return IdempotencyResult(
            created=False,
            user_turn=user_turn,
            existing_assistant_turn=existing_assistant,
            should_generate=False,
        )

    @staticmethod
    def _ensure_turn_id(turn: ConversationTurn) -> None:
        if turn.turn_id is None:
            turn.turn_id = uuid4().hex

    @staticmethod
    def _row_to_turn(row: sqlite3.Row) -> ConversationTurn:
        scope = MemoryScope(
            app=str(row["app"]),
            channel=str(row["channel"]),
            user_id=str(row["user_id"]),
            conversation_id=str(row["conversation_id"]),
            thread_id=str(row["thread_id"]),
            metadata=_json_loads(row["scope_metadata"]),
        )
        return ConversationTurn(
            turn_id=row["turn_id"],
            scope=scope,
            role=str(row["role"]),
            content=str(row["content"]),
            status=TurnStatus(str(row["status"])),
            source_message_id=row["source_message_id"],
            parent_turn_id=row["parent_turn_id"],
            request_message_id=row["request_message_id"],
            created_at=_datetime_from_text(str(row["created_at"])),
            metadata=_json_loads(row["metadata"]),
        )


def _json_dumps(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_loads(value: object) -> dict[str, Any]:
    if not isinstance(value, str) or not value:
        return {}
    loaded = json.loads(value)
    return loaded if isinstance(loaded, dict) else {}


def _datetime_to_text(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat(timespec="microseconds")


def _datetime_from_text(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)
