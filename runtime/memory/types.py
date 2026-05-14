# -*- coding: utf-8 -*-
"""Shared types for runtime conversation memory."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class MemoryMode(str, Enum):
    """Whether long-term memory is active for a request scope."""

    ON = "on"
    OFF = "off"


class TurnStatus(str, Enum):
    """Lifecycle states for user and assistant turns."""

    RECEIVED = "received"
    ACCEPTED = "accepted"
    DUPLICATE = "duplicate"
    GENERATING = "generating"
    ANSWERED = "answered"
    DELIVERING = "delivering"
    DELIVERED = "delivered"
    FAILED = "failed"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class MemoryScope:
    """Stable isolation key for one product conversation thread."""

    app: str
    channel: str
    user_id: str
    conversation_id: str
    thread_id: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def key(self) -> tuple[str, str, str, str, str]:
        return (self.app, self.channel, self.user_id, self.conversation_id, self.thread_id)


@dataclass
class ConversationTurn:
    """One user or assistant turn persisted by a MemoryStore."""

    scope: MemoryScope
    role: str
    content: str
    status: TurnStatus
    turn_id: Optional[str] = None
    source_message_id: Optional[str] = None
    parent_turn_id: Optional[str] = None
    request_message_id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_recent_context_eligible(self) -> bool:
        if self.role == "assistant":
            return self.status == TurnStatus.DELIVERED
        if self.role == "user":
            return self.status == TurnStatus.ACCEPTED
        return False


@dataclass(frozen=True)
class ChatInput:
    """Input to ConversationService for a single user message."""

    scope: MemoryScope
    message: str
    source_message_id: str
    memory_mode: MemoryMode = MemoryMode.ON
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChatOutput:
    """Result returned by ConversationService before product-specific delivery."""

    response: str
    prompt: str
    user_turn: Optional[ConversationTurn] = None
    assistant_turn: Optional[ConversationTurn] = None
    duplicate: bool = False
    reused_response: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class IdempotencyResult:
    """Result of appending a user turn under source-message idempotency."""

    created: bool
    user_turn: ConversationTurn
    existing_assistant_turn: Optional[ConversationTurn] = None
    should_generate: bool = True

    @property
    def has_delivered_response(self) -> bool:
        return (
            self.existing_assistant_turn is not None
            and self.existing_assistant_turn.status == TurnStatus.DELIVERED
        )
