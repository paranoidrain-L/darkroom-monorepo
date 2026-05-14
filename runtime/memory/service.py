# -*- coding: utf-8 -*-
"""Conversation orchestration on top of MemoryStore and AIClient."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any, Sequence
from uuid import uuid4

from runtime.clients.base import AIClient
from runtime.memory.policy import DEFAULT_MEMORY_POLICY, MemoryPolicy
from runtime.memory.store import MemoryStore
from runtime.memory.types import (
    ChatInput,
    ChatOutput,
    ConversationTurn,
    TurnStatus,
)


class ConversationService:
    """Build prompts, call an AI backend, and persist conversation turns."""

    def __init__(
        self,
        *,
        store: MemoryStore,
        ai_client: AIClient,
        policy: MemoryPolicy = DEFAULT_MEMORY_POLICY,
        summarizer: Callable[[str], str] | None = None,
        fact_extractor: Callable[[str], Sequence[str]] | None = None,
    ) -> None:
        self.store = store
        self.ai_client = ai_client
        self.policy = policy
        self.summarizer = summarizer
        self.fact_extractor = fact_extractor

    def chat(self, chat_input: ChatInput) -> ChatOutput:
        policy = self.policy.for_mode(chat_input.memory_mode)
        if not policy.memory_enabled:
            prompt = self._compose_prompt(
                current_message=chat_input.message,
                summary="",
                facts=[],
                recent_turns=[],
                policy=policy,
            )
            response = self.ai_client.chat(prompt)
            return ChatOutput(response=response, prompt=prompt)

        user_turn = ConversationTurn(
            turn_id=self._new_turn_id(),
            scope=chat_input.scope,
            role="user",
            content=chat_input.message,
            status=TurnStatus.ACCEPTED,
            source_message_id=chat_input.source_message_id,
            metadata=chat_input.metadata,
        )
        idempotency = self.store.append_user_turn(user_turn)

        if idempotency.has_delivered_response:
            assert idempotency.existing_assistant_turn is not None
            return ChatOutput(
                response=idempotency.existing_assistant_turn.content,
                prompt="",
                user_turn=idempotency.user_turn,
                assistant_turn=idempotency.existing_assistant_turn,
                duplicate=True,
                reused_response=True,
            )

        if not idempotency.should_generate:
            return ChatOutput(
                response="",
                prompt="",
                user_turn=idempotency.user_turn,
                duplicate=not idempotency.created,
                metadata={"skipped_generation": True},
            )

        recent_turns = [
            turn
            for turn in self.store.get_recent_turns(chat_input.scope, policy.recent_turn_limit)
            if turn.turn_id != idempotency.user_turn.turn_id
        ]
        summary = self.store.get_summary(chat_input.scope)
        facts = self.store.get_facts(chat_input.scope, policy.facts_limit)
        prompt = self._compose_prompt(
            current_message=chat_input.message,
            summary=summary,
            facts=facts,
            recent_turns=recent_turns,
            policy=policy,
        )
        response = self.ai_client.chat(prompt)

        assistant_turn = ConversationTurn(
            turn_id=self._new_turn_id(),
            scope=chat_input.scope,
            role="assistant",
            content=response,
            status=TurnStatus.ANSWERED,
            parent_turn_id=idempotency.user_turn.turn_id,
            request_message_id=chat_input.source_message_id,
            metadata={"source": "conversation_service"},
        )
        assistant_turn = self.store.append_assistant_turn(assistant_turn)
        postprocess_metadata = self._postprocess_memory(
            scope=chat_input.scope,
            policy=policy,
            current_turns=[idempotency.user_turn, assistant_turn],
            current_summary=summary,
        )

        return ChatOutput(
            response=response,
            prompt=prompt,
            user_turn=idempotency.user_turn,
            assistant_turn=assistant_turn,
            duplicate=not idempotency.created,
            metadata=postprocess_metadata,
        )

    def respond(self, chat_input: ChatInput) -> ChatOutput:
        return self.chat(chat_input)

    def mark_assistant_delivered(self, assistant_turn_id: str) -> None:
        self.store.update_turn_status(assistant_turn_id, TurnStatus.DELIVERED)

    def mark_assistant_failed(self, assistant_turn_id: str) -> None:
        self.store.update_turn_status(assistant_turn_id, TurnStatus.FAILED)

    def reset(self, scope: Any) -> None:
        self.store.clear_scope(scope)

    def get_summary(self, scope: Any) -> str:
        return self.store.get_summary(scope)

    def _postprocess_memory(
        self,
        *,
        scope: Any,
        policy: MemoryPolicy,
        current_turns: Sequence[ConversationTurn],
        current_summary: str,
    ) -> dict[str, Any]:
        metadata: dict[str, Any] = {}
        if not policy.memory_enabled:
            return metadata

        turn_count = self._get_turn_count(scope, current_turns)
        if self.summarizer is not None and self._should_refresh_summary(
            scope=scope,
            current_summary=current_summary,
            turn_count=turn_count,
            policy=policy,
        ):
            try:
                summary_input = self._render_summary_input(
                    current_summary,
                    self._get_turns_for_summary(scope, policy, current_turns),
                )
                summary = self.summarizer(summary_input).strip()
                if policy.enable_sensitive_filter:
                    summary = self._redact_sensitive_text(summary)
                summary = policy.truncate_text(summary, policy.max_summary_chars)
                if summary:
                    self._set_summary(scope, summary, turn_count)
                    metadata["summary_updated"] = True
            except Exception as exc:
                metadata["summary_error"] = str(exc)

        if policy.enable_fact_extraction and self.fact_extractor is not None:
            try:
                facts_input = self._render_turns_for_memory(current_turns)
                facts = self.fact_extractor(facts_input)
                added = 0
                existing_facts = {
                    fact.strip().casefold()
                    for fact in self.store.get_facts(scope, max(policy.facts_limit, 50))
                    if fact.strip()
                }
                for fact in facts[: policy.facts_limit]:
                    clean_fact = fact.strip()
                    if not self._is_explicit_fact(clean_fact):
                        continue
                    if policy.enable_sensitive_filter:
                        clean_fact = self._redact_sensitive_text(clean_fact)
                    clean_fact = policy.truncate_text(clean_fact, policy.max_fact_chars)
                    fact_key = clean_fact.casefold()
                    if clean_fact and fact_key not in existing_facts:
                        self._add_fact(scope, clean_fact)
                        existing_facts.add(fact_key)
                        added += 1
                if added:
                    metadata["facts_added"] = added
            except Exception as exc:
                metadata["facts_error"] = str(exc)

        return metadata

    def _should_refresh_summary(
        self,
        *,
        scope: Any,
        current_summary: str,
        turn_count: int,
        policy: MemoryPolicy,
    ) -> bool:
        if turn_count < policy.summary_after_turns:
            return False
        if not current_summary:
            return True
        if policy.summary_refresh_turns <= 0:
            return False
        summary_turn_count = self._get_summary_turn_count(scope)
        return turn_count - summary_turn_count >= policy.summary_refresh_turns

    def _get_turn_count(self, scope: Any, fallback_turns: Sequence[ConversationTurn]) -> int:
        get_turn_count = getattr(self.store, "get_turn_count", None)
        if get_turn_count is None:
            return len(fallback_turns)
        return int(get_turn_count(scope))

    def _get_summary_turn_count(self, scope: Any) -> int:
        get_summary_turn_count = getattr(self.store, "get_summary_turn_count", None)
        if get_summary_turn_count is None:
            return 0
        return int(get_summary_turn_count(scope))

    def _get_turns_for_summary(
        self,
        scope: Any,
        policy: MemoryPolicy,
        fallback_turns: Sequence[ConversationTurn],
    ) -> Sequence[ConversationTurn]:
        get_turns_for_summary = getattr(self.store, "get_turns_for_summary", None)
        if get_turns_for_summary is None:
            return fallback_turns

        limit = max(
            policy.recent_turn_limit,
            policy.summary_after_turns + max(policy.summary_refresh_turns, 0),
            12,
        )
        return get_turns_for_summary(scope, limit)

    def _set_summary(self, scope: Any, summary: str, turn_count: int) -> None:
        try:
            self.store.set_summary(scope, summary, turn_count=turn_count)
        except TypeError:
            self.store.set_summary(scope, summary)

    def _add_fact(self, scope: Any, fact: str) -> None:
        self.store.add_fact(scope, fact)

    @staticmethod
    def _is_explicit_fact(fact: str) -> bool:
        return bool(fact.strip())

    @staticmethod
    def _render_summary_input(
        current_summary: str,
        turns: Sequence[ConversationTurn],
    ) -> str:
        sections = []
        if current_summary.strip():
            sections.append(f"Existing summary:\n{current_summary.strip()}")
        rendered_turns = ConversationService._render_turns_for_memory(turns)
        if rendered_turns:
            sections.append(f"Recent conversation:\n{rendered_turns}")
        return "\n\n".join(sections)

    @staticmethod
    def _render_turns_for_memory(turns: Sequence[ConversationTurn]) -> str:
        lines = []
        for turn in turns:
            if not ConversationService._is_memory_compressible(turn):
                continue
            role = "Assistant" if turn.role == "assistant" else "User"
            lines.append(f"{role}: {turn.content.strip()}")
        return "\n".join(lines)

    @staticmethod
    def _is_memory_compressible(turn: ConversationTurn) -> bool:
        if turn.role == "user":
            return turn.status == TurnStatus.ACCEPTED
        if turn.role == "assistant":
            return turn.status in {TurnStatus.ANSWERED, TurnStatus.DELIVERED}
        return False

    @staticmethod
    def _redact_sensitive_text(text: str) -> str:
        patterns = [
            r"(?i)(api[_-]?key\s*[:=]\s*)[^\s,，;；]+",
            r"(?i)(token\s*[:=]\s*)[^\s,，;；]+",
            r"(?i)(password\s*[:=]\s*)[^\s,，;；]+",
            r"(?i)(secret\s*[:=]\s*)[^\s,，;；]+",
            r"(?i)(authorization:\s*bearer\s+)[^\s,，;；]+",
        ]
        redacted = text
        for pattern in patterns:
            redacted = re.sub(pattern, r"\1[REDACTED]", redacted)
        return redacted

    def _compose_prompt(
        self,
        *,
        current_message: str,
        summary: str,
        facts: Sequence[str],
        recent_turns: Sequence[ConversationTurn],
        policy: MemoryPolicy,
    ) -> str:
        sections: list[str] = []
        summary = policy.truncate_text(summary.strip(), policy.max_summary_chars)
        if summary:
            sections.append(f"Conversation summary:\n{summary}")

        clean_facts = [
            policy.truncate_text(fact.strip(), policy.max_fact_chars)
            for fact in facts
            if fact.strip()
        ]
        if clean_facts:
            facts_text = "\n".join(f"- {fact}" for fact in clean_facts)
            sections.append(f"Known facts:\n{facts_text}")

        recent_lines = []
        for turn in recent_turns[-policy.recent_turn_limit :]:
            if not turn.is_recent_context_eligible():
                continue
            label = "User" if turn.role == "user" else "Assistant"
            content = policy.truncate_text(turn.content.strip(), policy.max_turn_chars)
            recent_lines.append(f"{label}: {content}")
        if recent_lines:
            sections.append("Recent conversation:\n" + "\n".join(recent_lines))

        current = policy.truncate_text(current_message.strip(), policy.max_turn_chars)
        current_section = f"Current user message:\n{current}"
        prefix = "\n\n".join(sections).strip()
        return self._fit_prompt(prefix=prefix, current_section=current_section, policy=policy)

    @staticmethod
    def _fit_prompt(*, prefix: str, current_section: str, policy: MemoryPolicy) -> str:
        if not prefix:
            return MemoryPolicy.truncate_text(current_section, policy.max_prompt_chars)

        separator = "\n\n"
        available_for_prefix = policy.max_prompt_chars - len(current_section) - len(separator)
        if available_for_prefix <= 0:
            return MemoryPolicy.truncate_text(current_section, policy.max_prompt_chars)
        fitted_prefix = MemoryPolicy.truncate_text(prefix, available_for_prefix)
        prompt = f"{fitted_prefix}{separator}{current_section}"
        return MemoryPolicy.truncate_text(prompt, policy.max_prompt_chars)

    @staticmethod
    def _new_turn_id() -> str:
        return uuid4().hex
