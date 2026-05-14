# -*- coding: utf-8 -*-
"""Memory integration helpers for Feishu bot."""

from __future__ import annotations

from typing import Any, Callable

from products.feishu_bot.config import FeishuBotConfig
from runtime.memory import (
    ConversationService,
    InMemoryMemoryStore,
    MemoryMode,
    MemoryPolicy,
    MemoryScope,
    SQLiteMemoryStore,
)


class FeishuConversationService(ConversationService):
    """Compatibility shim for memory helper methods used by this product path."""

    def _get_turn_count(self, scope: Any, current_turns: list[Any]) -> int:
        return self.store.get_turn_count(scope)

    def _get_turns_for_summary(
        self,
        scope: Any,
        policy: MemoryPolicy,
        current_turns: list[Any] | None = None,
    ) -> list[Any]:
        limit = max(policy.recent_turn_limit, policy.summary_after_turns + policy.summary_refresh_turns)
        return list(self.store.get_turns_for_summary(scope, limit))

    def _render_summary_input(self, current_summary: str, turns: list[Any]) -> str:
        turns_text = self._render_turns_for_memory(turns)
        if current_summary.strip():
            return f"Existing summary:\n{current_summary.strip()}\n\nRecent turns:\n{turns_text}"
        return turns_text

    def _set_summary(self, scope: Any, summary: str, turn_count: int) -> None:
        self.store.set_summary(scope, summary, turn_count=turn_count)

    def _add_fact(self, scope: Any, fact: str) -> None:
        self.store.add_fact(scope, fact)

    @staticmethod
    def _is_explicit_fact(fact: str) -> bool:
        return bool(fact.strip())

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
        summary_turn_count = self.store.get_summary_turn_count(scope)
        return turn_count - summary_turn_count >= policy.summary_refresh_turns


class FeishuMemoryAdapter:
    """Owns memory service construction, scope mapping, and user memory modes."""

    def __init__(
        self,
        *,
        config: FeishuBotConfig,
        ai_client: Any,
        metrics: dict[str, int],
        summarizer: Callable[[str], str] | None,
        fact_extractor: Callable[[str], list[str]] | None,
        conversation_service: ConversationService | None = None,
    ) -> None:
        self.config = config
        self.ai_client = ai_client
        self.metrics = metrics
        self.conversation_service = conversation_service or self._create_conversation_service(
            summarizer=summarizer,
            fact_extractor=fact_extractor,
        )
        self._memory_modes: dict[str, MemoryMode] = {}

    def create_scope(
        self,
        *,
        sender_id: str,
        chat_id: str,
        chat_type: str,
        event_type: str,
    ) -> MemoryScope:
        resolved_chat_id = chat_id or "unknown"
        return MemoryScope(
            app="feishu_bot",
            channel="feishu",
            user_id=sender_id,
            conversation_id=resolved_chat_id,
            thread_id=resolved_chat_id,
            metadata={
                "chat_type": chat_type,
                "event_type": event_type,
            },
        )

    @staticmethod
    def context_key(scope: MemoryScope) -> str:
        return "|".join(scope.key())

    def memory_mode(self, scope: MemoryScope) -> MemoryMode:
        if not self.config.memory_enabled:
            return MemoryMode.OFF
        return self._memory_modes.get(self.context_key(scope), MemoryMode.ON)

    def handle_command(
        self,
        *,
        scope: MemoryScope,
        user_message: str,
        clear_pending_file: Callable[[str], None],
    ) -> str | None:
        command = user_message.strip().lower()
        if command == "/reset":
            self.conversation_service.reset(scope)
            clear_pending_file(self.context_key(scope))
            return "已重置当前会话记忆。"

        if command == "/summary":
            summary = self.conversation_service.get_summary(scope).strip()
            if summary:
                return summary
            return "当前会话暂无摘要。"

        if command == "/memory off":
            self._memory_modes[self.context_key(scope)] = MemoryMode.OFF
            return "已关闭当前会话记忆。"

        if command == "/memory on":
            if not self.config.memory_enabled:
                return "当前会话记忆已被灰度开关关闭。"
            self._memory_modes[self.context_key(scope)] = MemoryMode.ON
            return "已开启当前会话记忆。"

        return None

    def _create_conversation_service(
        self,
        *,
        summarizer: Callable[[str], str] | None,
        fact_extractor: Callable[[str], list[str]] | None,
    ) -> ConversationService:
        store_name = self.config.memory_store.strip().lower()
        if store_name == "sqlite":
            store = SQLiteMemoryStore(
                self.config.memory_db_path,
                busy_timeout_ms=self.config.memory_busy_timeout_ms,
            )
            if self.config.memory_cleanup_on_start and self.config.memory_retention_days > 0:
                cleanup_counts = store.cleanup_retention(self.config.memory_retention_days)
                self.metrics["memory_cleanup_deleted"] = sum(cleanup_counts.values())
        elif store_name in {"in_memory", "memory"}:
            store = InMemoryMemoryStore()
        else:
            raise ValueError(f"未知 memory_store: {self.config.memory_store!r}")

        policy = MemoryPolicy(
            recent_turn_limit=self.config.memory_recent_turn_limit,
            summary_after_turns=self.config.memory_summary_after_turns,
            summary_refresh_turns=self.config.memory_summary_refresh_turns,
            enable_fact_extraction=self.config.memory_enable_fact_extraction,
            enable_sensitive_filter=self.config.memory_enable_sensitive_filter,
        )
        return FeishuConversationService(
            store=store,
            ai_client=self.ai_client,
            policy=policy,
            summarizer=summarizer if self.config.memory_enable_auto_summary else None,
            fact_extractor=fact_extractor if self.config.memory_enable_fact_extraction else None,
        )


def summarize_memory(ai_client: Any, conversation_text: str) -> str:
    prompt = (
        "请用中文为下面对话生成简洁摘要，只保留后续对话需要的事实、任务状态和用户偏好。"
        "不要保留密钥、token、密码等敏感信息。\n\n"
        f"{conversation_text}"
    )
    return ai_client.chat(prompt)


def extract_explicit_facts(conversation_text: str) -> list[str]:
    facts: list[str] = []
    markers = ("记住：", "记住:", "remember:", "fact:", "事实：", "事实:")
    for line in conversation_text.splitlines():
        lowered = line.lower()
        for marker in markers:
            index = lowered.find(marker.lower())
            if index < 0:
                continue
            fact = line[index + len(marker) :].strip()
            if fact:
                facts.append(fact)
            break
    return facts
