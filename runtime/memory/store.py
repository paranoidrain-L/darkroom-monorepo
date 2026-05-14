# -*- coding: utf-8 -*-
"""Storage protocol and lightweight in-memory store for conversation memory."""

from __future__ import annotations

from typing import Protocol, Sequence

from runtime.memory.types import ConversationTurn, IdempotencyResult, MemoryScope, TurnStatus


class MemoryStore(Protocol):
    """Source-of-truth storage API used by ConversationService."""

    def append_user_turn(self, turn: ConversationTurn) -> IdempotencyResult:
        """Append a user turn idempotently by source_message_id."""
        ...

    def append_assistant_turn(self, turn: ConversationTurn) -> ConversationTurn:
        """Append an assistant turn linked to its user request."""
        ...

    def update_turn_status(self, turn_id: str, status: TurnStatus) -> None:
        """Update a turn lifecycle status after delivery or failure."""
        ...

    def get_recent_turns(self, scope: MemoryScope, limit: int) -> Sequence[ConversationTurn]:
        """Return recent context-eligible turns for this scope."""
        ...

    def get_turns_for_summary(self, scope: MemoryScope, limit: int) -> Sequence[ConversationTurn]:
        """Return recent persisted turns, including not-yet-delivered assistant turns."""
        ...

    def get_turn_count(self, scope: MemoryScope) -> int:
        """Return the number of persisted turns in this scope."""
        ...

    def get_summary(self, scope: MemoryScope) -> str:
        """Return current thread summary, or an empty string."""
        ...

    def get_summary_turn_count(self, scope: MemoryScope) -> int:
        """Return the turn count captured by the latest summary, or zero."""
        ...

    def set_summary(self, scope: MemoryScope, summary: str, *, turn_count: int | None = None) -> None:
        """Persist current thread summary."""
        ...

    def get_facts(self, scope: MemoryScope, limit: int) -> Sequence[str]:
        """Return thread-scoped facts for prompt injection."""
        ...

    def add_fact(self, scope: MemoryScope, fact: str) -> None:
        """Persist one thread-scoped fact."""
        ...

    def clear_scope(self, scope: MemoryScope) -> None:
        """Clear turns, summary, facts, and ephemeral state for one scope."""
        ...

    def cleanup_retention(self, retention_days: int) -> dict[str, int]:
        """Delete expired memory rows and return deletion counts."""
        ...


class InMemoryMemoryStore:
    """Small MemoryStore useful before the SQLite implementation exists."""

    def __init__(self) -> None:
        self._turns: list[ConversationTurn] = []
        self._summaries: dict[tuple[str, str, str, str, str], str] = {}
        self._summary_turn_counts: dict[tuple[str, str, str, str, str], int] = {}
        self._facts: dict[tuple[str, str, str, str, str], list[str]] = {}

    def append_user_turn(self, turn: ConversationTurn) -> IdempotencyResult:
        if turn.source_message_id is None:
            self._turns.append(turn)
            return IdempotencyResult(created=True, user_turn=turn)

        existing = self._get_user_turn_by_source_id(turn.scope, turn.source_message_id)
        if existing is not None:
            existing_assistant = self._get_delivered_assistant_for_source_id(
                turn.scope,
                turn.source_message_id,
            )
            return IdempotencyResult(
                created=False,
                user_turn=existing,
                existing_assistant_turn=existing_assistant,
                should_generate=existing_assistant is None,
            )

        self._turns.append(turn)
        return IdempotencyResult(created=True, user_turn=turn)

    def append_assistant_turn(self, turn: ConversationTurn) -> ConversationTurn:
        self._turns.append(turn)
        return turn

    def update_turn_status(self, turn_id: str, status: TurnStatus) -> None:
        for turn in self._turns:
            if turn.turn_id == turn_id:
                turn.status = status
                return
        raise KeyError(f"turn not found: {turn_id}")

    def get_recent_turns(self, scope: MemoryScope, limit: int) -> Sequence[ConversationTurn]:
        scope_key = scope.key()
        eligible = [
            turn
            for turn in self._turns
            if turn.scope.key() == scope_key and turn.is_recent_context_eligible()
        ]
        return eligible[-limit:]

    def get_turns_for_summary(self, scope: MemoryScope, limit: int) -> Sequence[ConversationTurn]:
        if limit <= 0:
            return []
        scope_key = scope.key()
        turns = [turn for turn in self._turns if turn.scope.key() == scope_key]
        return turns[-limit:]

    def get_turn_count(self, scope: MemoryScope) -> int:
        scope_key = scope.key()
        return sum(1 for turn in self._turns if turn.scope.key() == scope_key)

    def get_summary(self, scope: MemoryScope) -> str:
        return self._summaries.get(scope.key(), "")

    def get_summary_turn_count(self, scope: MemoryScope) -> int:
        return self._summary_turn_counts.get(scope.key(), 0)

    def set_summary(self, scope: MemoryScope, summary: str, *, turn_count: int | None = None) -> None:
        self._summaries[scope.key()] = summary
        if turn_count is not None:
            self._summary_turn_counts[scope.key()] = turn_count

    def get_facts(self, scope: MemoryScope, limit: int) -> Sequence[str]:
        return self._facts.get(scope.key(), [])[:limit]

    def add_fact(self, scope: MemoryScope, fact: str) -> None:
        self._facts.setdefault(scope.key(), []).append(fact)

    def clear_scope(self, scope: MemoryScope) -> None:
        scope_key = scope.key()
        self._turns = [turn for turn in self._turns if turn.scope.key() != scope_key]
        self._summaries.pop(scope_key, None)
        self._summary_turn_counts.pop(scope_key, None)
        self._facts.pop(scope_key, None)

    def cleanup_retention(self, retention_days: int) -> dict[str, int]:
        if retention_days <= 0:
            return _empty_cleanup_counts()
        return _empty_cleanup_counts()

    def _get_user_turn_by_source_id(
        self,
        scope: MemoryScope,
        source_message_id: str,
    ) -> ConversationTurn | None:
        scope_key = scope.key()
        for turn in self._turns:
            if (
                turn.scope.key() == scope_key
                and turn.role == "user"
                and turn.source_message_id == source_message_id
            ):
                return turn
        return None

    def _get_delivered_assistant_for_source_id(
        self,
        scope: MemoryScope,
        source_message_id: str,
    ) -> ConversationTurn | None:
        scope_key = scope.key()
        for turn in reversed(self._turns):
            if (
                turn.scope.key() == scope_key
                and turn.role == "assistant"
                and turn.request_message_id == source_message_id
                and turn.status == TurnStatus.DELIVERED
            ):
                return turn
        return None


def _empty_cleanup_counts() -> dict[str, int]:
    return {
        "conversation_turns": 0,
        "conversation_summaries": 0,
        "memory_facts": 0,
    }
