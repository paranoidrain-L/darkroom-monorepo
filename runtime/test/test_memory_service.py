# -*- coding: utf-8 -*-
"""Tests for runtime conversation memory service."""

from __future__ import annotations

from runtime.memory import (
    ChatInput,
    ConversationService,
    ConversationTurn,
    IdempotencyResult,
    MemoryMode,
    MemoryPolicy,
    MemoryScope,
    TurnStatus,
)


class FakeAIClient:
    def __init__(self, response: str = "assistant response") -> None:
        self.response = response
        self.prompts: list[str] = []

    def chat(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.response


class FakeMemoryStore:
    def __init__(self) -> None:
        self.turns: list[ConversationTurn] = []
        self.user_by_source: dict[str, ConversationTurn] = {}
        self.summary = ""
        self.facts: list[str] = []
        self.cleared: list[MemoryScope] = []
        self.status_updates: list[tuple[str, TurnStatus]] = []
        self.summary_updates: list[str] = []
        self.fact_updates: list[str] = []

    def append_user_turn(self, turn: ConversationTurn) -> IdempotencyResult:
        assert turn.source_message_id is not None
        existing = self.user_by_source.get(turn.source_message_id)
        if existing is not None:
            existing_assistant = self._delivered_assistant_for(turn.source_message_id)
            return IdempotencyResult(
                created=False,
                user_turn=existing,
                existing_assistant_turn=existing_assistant,
                should_generate=existing_assistant is None,
            )

        self.user_by_source[turn.source_message_id] = turn
        self.turns.append(turn)
        return IdempotencyResult(created=True, user_turn=turn)

    def append_assistant_turn(self, turn: ConversationTurn) -> ConversationTurn:
        self.turns.append(turn)
        return turn

    def update_turn_status(self, turn_id: str, status: TurnStatus) -> None:
        self.status_updates.append((turn_id, status))
        for turn in self.turns:
            if turn.turn_id == turn_id:
                turn.status = status
                return

    def get_recent_turns(self, scope: MemoryScope, limit: int) -> list[ConversationTurn]:
        scoped = [
            turn
            for turn in self.turns
            if turn.scope.key() == scope.key() and turn.is_recent_context_eligible()
        ]
        return scoped[-limit:]

    def get_summary(self, scope: MemoryScope) -> str:
        return self.summary

    def set_summary(self, scope: MemoryScope, summary: str) -> None:
        self.summary = summary
        self.summary_updates.append(summary)

    def get_facts(self, scope: MemoryScope, limit: int) -> list[str]:
        return self.facts[:limit]

    def add_fact(self, scope: MemoryScope, fact: str) -> None:
        self.facts.append(fact)
        self.fact_updates.append(fact)

    def clear_scope(self, scope: MemoryScope) -> None:
        self.cleared.append(scope)

    def _delivered_assistant_for(self, source_message_id: str) -> ConversationTurn | None:
        for turn in reversed(self.turns):
            if (
                turn.role == "assistant"
                and turn.request_message_id == source_message_id
                and turn.status == TurnStatus.DELIVERED
            ):
                return turn
        return None


def make_scope(thread_id: str = "oc_chat_1") -> MemoryScope:
    return MemoryScope(
        app="feishu_bot",
        channel="feishu",
        user_id="ou_user_1",
        conversation_id="oc_chat_1",
        thread_id=thread_id,
        metadata={"chat_type": "p2p"},
    )


def test_service_composes_prompt_from_memory_layers() -> None:
    scope = make_scope()
    store = FakeMemoryStore()
    store.summary = "用户正在排查飞书机器人 memory。"
    store.facts = ["用户偏好中文回复"]
    store.turns.extend(
        [
            ConversationTurn(
                turn_id="u1",
                scope=scope,
                role="user",
                content="上一轮问题",
                status=TurnStatus.ACCEPTED,
                source_message_id="m0",
            ),
            ConversationTurn(
                turn_id="a1",
                scope=scope,
                role="assistant",
                content="上一轮回答",
                status=TurnStatus.DELIVERED,
                request_message_id="m0",
            ),
            ConversationTurn(
                turn_id="a2",
                scope=scope,
                role="assistant",
                content="没有投递成功的回答",
                status=TurnStatus.ANSWERED,
                request_message_id="m_failed",
            ),
        ]
    )
    ai_client = FakeAIClient(response="新回答")
    service = ConversationService(store=store, ai_client=ai_client)

    output = service.chat(ChatInput(scope=scope, message="继续说明", source_message_id="m1"))

    assert output.response == "新回答"
    prompt = ai_client.prompts[-1]
    assert "Conversation summary:" in prompt
    assert "用户正在排查飞书机器人 memory。" in prompt
    assert "Known facts:" in prompt
    assert "用户偏好中文回复" in prompt
    assert "上一轮问题" in prompt
    assert "上一轮回答" in prompt
    assert "没有投递成功的回答" not in prompt
    assert output.assistant_turn is not None
    assert output.assistant_turn.status == TurnStatus.ANSWERED


def test_duplicate_delivered_message_reuses_response_without_calling_ai() -> None:
    scope = make_scope()
    store = FakeMemoryStore()
    user_turn = ConversationTurn(
        turn_id="u1",
        scope=scope,
        role="user",
        content="原始问题",
        status=TurnStatus.ACCEPTED,
        source_message_id="m1",
    )
    assistant_turn = ConversationTurn(
        turn_id="a1",
        scope=scope,
        role="assistant",
        content="历史已投递回答",
        status=TurnStatus.DELIVERED,
        parent_turn_id="u1",
        request_message_id="m1",
    )
    store.user_by_source["m1"] = user_turn
    store.turns.extend([user_turn, assistant_turn])
    ai_client = FakeAIClient(response="不应调用")
    service = ConversationService(store=store, ai_client=ai_client)

    output = service.chat(ChatInput(scope=scope, message="原始问题", source_message_id="m1"))

    assert output.response == "历史已投递回答"
    assert output.duplicate is True
    assert output.reused_response is True
    assert ai_client.prompts == []


def test_memory_off_does_not_read_or_write_long_term_memory() -> None:
    scope = make_scope()
    store = FakeMemoryStore()
    store.summary = "不应注入的摘要"
    store.facts = ["不应注入的事实"]
    ai_client = FakeAIClient(response="无记忆回答")
    service = ConversationService(store=store, ai_client=ai_client)

    output = service.chat(
        ChatInput(
            scope=scope,
            message="临时问题",
            source_message_id="m1",
            memory_mode=MemoryMode.OFF,
        )
    )

    assert output.response == "无记忆回答"
    assert store.turns == []
    assert store.user_by_source == {}
    assert "不应注入" not in ai_client.prompts[-1]
    assert "临时问题" in ai_client.prompts[-1]


def test_prompt_hard_limit_keeps_current_message() -> None:
    scope = make_scope()
    store = FakeMemoryStore()
    store.summary = "S" * 200
    store.facts = ["F" * 200]
    ai_client = FakeAIClient()
    service = ConversationService(
        store=store,
        ai_client=ai_client,
        policy=MemoryPolicy(max_prompt_chars=120, max_turn_chars=80, max_summary_chars=80),
    )

    service.chat(ChatInput(scope=scope, message="当前问题必须保留", source_message_id="m1"))

    prompt = ai_client.prompts[-1]
    assert len(prompt) <= 120
    assert "当前问题必须保留" in prompt


def test_prompt_hard_limit_with_long_history_keeps_current_message() -> None:
    scope = make_scope()
    store = FakeMemoryStore()
    for index in range(20):
        store.turns.append(
            ConversationTurn(
                turn_id=f"u{index}",
                scope=scope,
                role="user",
                content=f"历史用户消息 {index} " + ("U" * 300),
                status=TurnStatus.ACCEPTED,
                source_message_id=f"m{index}",
            )
        )
        store.turns.append(
            ConversationTurn(
                turn_id=f"a{index}",
                scope=scope,
                role="assistant",
                content=f"历史助手回答 {index} " + ("A" * 300),
                status=TurnStatus.DELIVERED,
                request_message_id=f"m{index}",
            )
        )
    store.summary = "摘要 " + ("S" * 600)
    store.facts = ["事实 " + ("F" * 300)]
    ai_client = FakeAIClient(response="回答")
    service = ConversationService(
        store=store,
        ai_client=ai_client,
        policy=MemoryPolicy(
            recent_turn_limit=20,
            facts_limit=5,
            max_prompt_chars=500,
            max_turn_chars=160,
            max_summary_chars=160,
            max_fact_chars=120,
            summary_after_turns=99,
        ),
    )

    service.chat(ChatInput(scope=scope, message="当前问题必须保留在长历史下", source_message_id="m_new"))

    prompt = ai_client.prompts[-1]
    assert len(prompt) <= 500
    assert "当前问题必须保留在长历史下" in prompt


def test_delivery_status_helpers_delegate_to_store() -> None:
    scope = make_scope()
    store = FakeMemoryStore()
    ai_client = FakeAIClient()
    service = ConversationService(store=store, ai_client=ai_client)

    output = service.chat(ChatInput(scope=scope, message="hello", source_message_id="m1"))
    assert output.assistant_turn is not None

    service.mark_assistant_delivered(output.assistant_turn.turn_id or "")
    service.mark_assistant_failed(output.assistant_turn.turn_id or "")

    assert store.status_updates == [
        (output.assistant_turn.turn_id, TurnStatus.DELIVERED),
        (output.assistant_turn.turn_id, TurnStatus.FAILED),
    ]


def test_summary_refresh_runs_after_threshold_and_redacts_sensitive_values() -> None:
    scope = make_scope()
    store = FakeMemoryStore()
    ai_client = FakeAIClient(response="api_key=assistant-secret")
    summarizer_inputs: list[str] = []

    def summarizer(text: str) -> str:
        summarizer_inputs.append(text)
        return "用户提供了 token: user-secret，助手返回了 api_key=assistant-secret"

    service = ConversationService(
        store=store,
        ai_client=ai_client,
        policy=MemoryPolicy(summary_after_turns=2, summary_refresh_turns=2),
        summarizer=summarizer,
    )

    output = service.chat(ChatInput(scope=scope, message="token: user-secret", source_message_id="m1"))

    assert output.metadata["summary_updated"] is True
    assert summarizer_inputs
    assert "User: token: user-secret" in summarizer_inputs[-1]
    assert "Assistant: api_key=assistant-secret" in summarizer_inputs[-1]
    assert store.summary == "用户提供了 token: [REDACTED]，助手返回了 api_key=[REDACTED]"
    assert store.summary_updates == ["用户提供了 token: [REDACTED]，助手返回了 api_key=[REDACTED]"]


def test_summary_failure_does_not_block_response() -> None:
    scope = make_scope()
    store = FakeMemoryStore()
    ai_client = FakeAIClient(response="ok")

    def broken_summarizer(text: str) -> str:
        raise RuntimeError("summary backend down")

    service = ConversationService(
        store=store,
        ai_client=ai_client,
        policy=MemoryPolicy(summary_after_turns=2),
        summarizer=broken_summarizer,
    )

    output = service.chat(ChatInput(scope=scope, message="hello", source_message_id="m1"))

    assert output.response == "ok"
    assert output.metadata["summary_error"] == "summary backend down"
    assert store.summary == ""


def test_fact_extraction_is_disabled_by_default() -> None:
    scope = make_scope()
    store = FakeMemoryStore()
    ai_client = FakeAIClient(response="ok")
    calls: list[str] = []

    def fact_extractor(text: str) -> list[str]:
        calls.append(text)
        return ["用户偏好中文"]

    service = ConversationService(store=store, ai_client=ai_client, fact_extractor=fact_extractor)

    output = service.chat(ChatInput(scope=scope, message="hello", source_message_id="m1"))

    assert output.response == "ok"
    assert calls == []
    assert store.facts == []


def test_fact_extraction_when_enabled_is_limited_and_redacted() -> None:
    scope = make_scope()
    store = FakeMemoryStore()
    ai_client = FakeAIClient(response="ok")

    def fact_extractor(text: str) -> list[str]:
        return [
            "用户偏好中文",
            "password=super-secret",
            "extra fact",
        ]

    service = ConversationService(
        store=store,
        ai_client=ai_client,
        policy=MemoryPolicy(enable_fact_extraction=True, facts_limit=2),
        fact_extractor=fact_extractor,
    )

    output = service.chat(ChatInput(scope=scope, message="hello", source_message_id="m1"))

    assert output.metadata["facts_added"] == 2
    assert store.facts == ["用户偏好中文", "password=[REDACTED]"]
    assert store.fact_updates == ["用户偏好中文", "password=[REDACTED]"]
