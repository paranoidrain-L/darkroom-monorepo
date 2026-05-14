# -*- coding: utf-8 -*-
"""Tests for the rewritten lark-cli based Feishu bot."""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import unittest
from dataclasses import fields
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from products.feishu_bot.bot import ConversationLogger, FeishuBot
from products.feishu_bot.config import FeishuBotConfig
from products.feishu_bot.handlers.context import FileInfo, SessionContextManager
from products.feishu_bot.lark_cli import LarkCLI, LarkCLIError
from runtime.memory import (
    ChatInput,
    ChatOutput,
    ConversationTurn,
    InMemoryMemoryStore,
    MemoryMode,
    MemoryScope,
    SQLiteMemoryStore,
    TurnStatus,
)


class FakeAIClient:
    def __init__(self, response: str = "ok") -> None:
        self.response = response
        self.prompts: list[str] = []

    def chat(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.response


class FakeLarkCLI:
    def __init__(self, *, fail_replies: bool = False) -> None:
        self.replies: list[tuple[str, str]] = []
        self.downloads: list[tuple[str, str, str]] = []
        self.fail_replies = fail_replies

    def ensure_available(self) -> None:
        return None

    def show_config(self) -> dict:
        return {"appId": "cli_test"}

    def reply_text(self, message_id: str, content: str) -> dict:
        if self.fail_replies:
            raise LarkCLIError("reply failed")
        self.replies.append((message_id, content))
        return {"code": 0}

    def download_message_resource(self, *, message_id: str, file_key: str, output_path: str, resource_type: str):
        self.downloads.append((message_id, file_key, output_path))
        full_path = Path(output_path)
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text("hello world", encoding="utf-8")
        return str(full_path)


class FakeConversationService:
    def __init__(self, response: str = "memory answer", assistant_turn_id: str = "assistant_1") -> None:
        self.response = response
        self.assistant_turn_id = assistant_turn_id
        self.inputs: list[ChatInput] = []
        self.delivered: list[str] = []
        self.failed: list[str] = []
        self.reset_scopes: list[MemoryScope] = []
        self.summary = ""

    def chat(self, chat_input: ChatInput) -> ChatOutput:
        self.inputs.append(chat_input)
        assistant_turn = ConversationTurn(
            turn_id=self.assistant_turn_id,
            scope=chat_input.scope,
            role="assistant",
            content=self.response,
            status=TurnStatus.ANSWERED,
            request_message_id=chat_input.source_message_id,
        )
        return ChatOutput(response=self.response, prompt="fake prompt", assistant_turn=assistant_turn)

    def respond(self, chat_input: ChatInput) -> ChatOutput:
        return self.chat(chat_input)

    def mark_assistant_delivered(self, assistant_turn_id: str) -> None:
        self.delivered.append(assistant_turn_id)

    def mark_assistant_failed(self, assistant_turn_id: str) -> None:
        self.failed.append(assistant_turn_id)

    def reset(self, scope: MemoryScope) -> None:
        self.reset_scopes.append(scope)

    def get_summary(self, scope: MemoryScope) -> str:
        return self.summary


def build_bot_with_conversation_service(
    config: FeishuBotConfig,
    *,
    ai_client: FakeAIClient,
    lark_cli: FakeLarkCLI,
    conversation_service: FakeConversationService,
    context_manager: SessionContextManager | None = None,
) -> FeishuBot:
    try:
        return FeishuBot(
            config,
            ai_client=ai_client,
            lark_cli=lark_cli,
            context_manager=context_manager,
            conversation_service=conversation_service,
        )
    except TypeError as exc:
        if "conversation_service" not in str(exc):
            raise

    bot = FeishuBot(
        config,
        ai_client=ai_client,
        lark_cli=lark_cli,
        context_manager=context_manager,
    )
    bot.conversation_service = conversation_service
    return bot


def build_event(
    message_type: str,
    content: dict,
    *,
    sender_id: str = "ou_test",
    chat_id: str = "oc_chat_1",
    chat_type: str = "p2p",
    message_id: str = "om_message_1",
):
    return {
        "schema": "2.0",
        "header": {"event_type": "im.message.receive_v1"},
        "event": {
            "sender": {
                "sender_id": {"open_id": sender_id},
                "sender_type": "user",
            },
            "message": {
                "message_id": message_id,
                "chat_id": chat_id,
                "chat_type": chat_type,
                "message_type": message_type,
                "content": json.dumps(content, ensure_ascii=False),
            },
        },
    }


def feishu_scope_key(sender_id: str = "ou_test", chat_id: str = "oc_chat_1") -> tuple[str, str, str, str, str]:
    return ("feishu_bot", "feishu", sender_id, chat_id, chat_id)


def feishu_context_key(sender_id: str = "ou_test", chat_id: str = "oc_chat_1") -> str:
    return "|".join(feishu_scope_key(sender_id, chat_id))


class TestFeishuBotConfig(unittest.TestCase):
    def test_memory_trial_example_config_validates_when_present(self) -> None:
        example_path = Path("config/feishu_bot.example.json")
        if not example_path.exists():
            self.skipTest("config/feishu_bot.example.json is not present")

        config = FeishuBotConfig.from_json(str(example_path))

        self.assertTrue(config.validate())
        self.assertEqual(config.memory_store, "sqlite")
        self.assertEqual(config.memory_db_path, "data/feishu_bot_memory.sqlite3")
        self.assertEqual(config.memory_busy_timeout_ms, 5000)
        self.assertEqual(config.memory_recent_turn_limit, 8)
        self.assertEqual(config.memory_summary_after_turns, 12)
        self.assertEqual(config.memory_summary_refresh_turns, 6)
        self.assertFalse(config.allow_group_chats)
        self.assertFalse(config.memory_enable_auto_summary)
        self.assertFalse(config.memory_enable_fact_extraction)
        self.assertTrue(config.memory_enable_sensitive_filter)
        self.assertTrue(config.memory_enabled)
        self.assertEqual(config.memory_retention_days, 0)
        self.assertFalse(config.memory_cleanup_on_start)
        self.assertTrue(config.memory_log_redaction)
        self.assertTrue(config.memory_trace_enabled)

    def test_memory_trial_docs_only_use_supported_config_fields(self) -> None:
        supported_json_fields = {field.name for field in fields(FeishuBotConfig)}
        supported_env_vars = {
            "FEISHU_APP_ID",
            "FEISHU_APP_SECRET",
            "FEISHU_BACKEND",
            "FEISHU_USE_CLAUDE",
            "FEISHU_MODEL",
            "FEISHU_AGENT",
            "TRAE_CLI_PATH",
            "FEISHU_TIMEOUT",
            "LARK_CLI_PATH",
            "FEISHU_LOG_DIR",
            "FEISHU_DOWNLOAD_DIR",
            "FEISHU_SESSION_TTL",
            "FEISHU_ALLOW_GROUP_CHATS",
            "FEISHU_WORKER_QUEUE_SIZE",
            "FEISHU_EVENT_TYPES",
            "FEISHU_MEMORY_STORE",
            "FEISHU_MEMORY_DB_PATH",
            "FEISHU_MEMORY_BUSY_TIMEOUT_MS",
            "FEISHU_MEMORY_RECENT_TURN_LIMIT",
            "FEISHU_MEMORY_SUMMARY_AFTER_TURNS",
            "FEISHU_MEMORY_SUMMARY_REFRESH_TURNS",
            "FEISHU_MEMORY_ENABLE_AUTO_SUMMARY",
            "FEISHU_MEMORY_ENABLE_FACT_EXTRACTION",
            "FEISHU_MEMORY_ENABLE_SENSITIVE_FILTER",
            "FEISHU_MEMORY_ENABLED",
            "FEISHU_MEMORY_RETENTION_DAYS",
            "FEISHU_MEMORY_CLEANUP_ON_START",
            "FEISHU_MEMORY_LOG_REDACTION",
            "FEISHU_MEMORY_TRACE_ENABLED",
        }
        doc_paths = [
            Path("products/feishu_bot/README.md"),
        ]

        for doc_path in doc_paths:
            text = doc_path.read_text(encoding="utf-8")
            for match in re.finditer(r"```json\n(.*?)\n```", text, re.DOTALL):
                config_doc = json.loads(match.group(1))
                unknown_fields = set(config_doc) - supported_json_fields
                self.assertEqual(unknown_fields, set(), str(doc_path))

            documented_env_vars = set(re.findall(r"^export\s+([A-Z0-9_]+)=", text, re.MULTILINE))
            unknown_env_vars = documented_env_vars - supported_env_vars
            self.assertEqual(unknown_env_vars, set(), str(doc_path))

    def test_from_json_supports_new_fields(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(
                {
                    "lark_cli_path": "/usr/local/bin/lark-cli",
                    "allow_group_chats": True,
                    "session_ttl": 90,
                    "event_types": "im.message.receive_v1",
                    "memory_store": "sqlite",
                    "memory_db_path": "/tmp/feishu-memory.sqlite3",
                    "memory_busy_timeout_ms": 7000,
                    "memory_recent_turn_limit": 4,
                    "memory_summary_after_turns": 5,
                    "memory_summary_refresh_turns": 3,
                    "memory_enable_auto_summary": True,
                    "memory_enable_fact_extraction": True,
                    "memory_enable_sensitive_filter": False,
                    "memory_enabled": False,
                    "memory_retention_days": 30,
                    "memory_cleanup_on_start": True,
                    "memory_log_redaction": False,
                    "memory_trace_enabled": False,
                },
                f,
            )
            temp_path = f.name

        try:
            config = FeishuBotConfig.from_json(temp_path)
        finally:
            Path(temp_path).unlink()

        self.assertEqual(config.lark_cli_path, "/usr/local/bin/lark-cli")
        self.assertTrue(config.allow_group_chats)
        self.assertEqual(config.session_ttl, 90)
        self.assertEqual(config.event_types, "im.message.receive_v1")
        self.assertEqual(config.memory_store, "sqlite")
        self.assertEqual(config.memory_db_path, "/tmp/feishu-memory.sqlite3")
        self.assertEqual(config.memory_busy_timeout_ms, 7000)
        self.assertEqual(config.memory_recent_turn_limit, 4)
        self.assertEqual(config.memory_summary_after_turns, 5)
        self.assertEqual(config.memory_summary_refresh_turns, 3)
        self.assertTrue(config.memory_enable_auto_summary)
        self.assertTrue(config.memory_enable_fact_extraction)
        self.assertFalse(config.memory_enable_sensitive_filter)
        self.assertFalse(config.memory_enabled)
        self.assertEqual(config.memory_retention_days, 30)
        self.assertTrue(config.memory_cleanup_on_start)
        self.assertFalse(config.memory_log_redaction)
        self.assertFalse(config.memory_trace_enabled)

    def test_validate_without_explicit_app_secret(self) -> None:
        config = FeishuBotConfig()
        self.assertTrue(config.validate())

    def test_memory_config_from_env(self) -> None:
        with patch.dict(
            os.environ,
            {
                "FEISHU_MEMORY_STORE": "sqlite",
                "FEISHU_MEMORY_DB_PATH": "/tmp/env-memory.sqlite3",
                "FEISHU_MEMORY_BUSY_TIMEOUT_MS": "9000",
                "FEISHU_MEMORY_RECENT_TURN_LIMIT": "6",
                "FEISHU_MEMORY_SUMMARY_AFTER_TURNS": "7",
                "FEISHU_MEMORY_SUMMARY_REFRESH_TURNS": "4",
                "FEISHU_MEMORY_ENABLE_AUTO_SUMMARY": "true",
                "FEISHU_MEMORY_ENABLE_FACT_EXTRACTION": "true",
                "FEISHU_MEMORY_ENABLE_SENSITIVE_FILTER": "false",
                "FEISHU_MEMORY_ENABLED": "false",
                "FEISHU_MEMORY_RETENTION_DAYS": "31",
                "FEISHU_MEMORY_CLEANUP_ON_START": "true",
                "FEISHU_MEMORY_LOG_REDACTION": "false",
                "FEISHU_MEMORY_TRACE_ENABLED": "false",
            },
        ):
            config = FeishuBotConfig()

        self.assertEqual(config.memory_store, "sqlite")
        self.assertEqual(config.memory_db_path, "/tmp/env-memory.sqlite3")
        self.assertEqual(config.memory_busy_timeout_ms, 9000)
        self.assertEqual(config.memory_recent_turn_limit, 6)
        self.assertEqual(config.memory_summary_after_turns, 7)
        self.assertEqual(config.memory_summary_refresh_turns, 4)
        self.assertTrue(config.memory_enable_auto_summary)
        self.assertTrue(config.memory_enable_fact_extraction)
        self.assertFalse(config.memory_enable_sensitive_filter)
        self.assertFalse(config.memory_enabled)
        self.assertEqual(config.memory_retention_days, 31)
        self.assertTrue(config.memory_cleanup_on_start)
        self.assertFalse(config.memory_log_redaction)
        self.assertFalse(config.memory_trace_enabled)

    def test_to_dict_includes_memory_config(self) -> None:
        config = FeishuBotConfig(
            memory_store="sqlite",
            memory_db_path="/tmp/dict-memory.sqlite3",
            memory_busy_timeout_ms=8000,
            memory_recent_turn_limit=6,
            memory_summary_after_turns=7,
            memory_summary_refresh_turns=4,
            memory_enable_auto_summary=True,
            memory_enable_fact_extraction=True,
            memory_enable_sensitive_filter=False,
            memory_enabled=False,
            memory_retention_days=32,
            memory_cleanup_on_start=True,
            memory_log_redaction=False,
            memory_trace_enabled=False,
        )

        result = config.to_dict()

        self.assertEqual(result["memory_store"], "sqlite")
        self.assertEqual(result["memory_db_path"], "/tmp/dict-memory.sqlite3")
        self.assertEqual(result["memory_busy_timeout_ms"], 8000)
        self.assertEqual(result["memory_recent_turn_limit"], 6)
        self.assertEqual(result["memory_summary_after_turns"], 7)
        self.assertEqual(result["memory_summary_refresh_turns"], 4)
        self.assertTrue(result["memory_enable_auto_summary"])
        self.assertTrue(result["memory_enable_fact_extraction"])
        self.assertFalse(result["memory_enable_sensitive_filter"])
        self.assertFalse(result["memory_enabled"])
        self.assertEqual(result["memory_retention_days"], 32)
        self.assertTrue(result["memory_cleanup_on_start"])
        self.assertFalse(result["memory_log_redaction"])
        self.assertFalse(result["memory_trace_enabled"])


class TestLarkCLI(unittest.TestCase):
    @patch("products.feishu_bot.lark_cli.subprocess.run")
    def test_reply_text_uses_messages_reply_shortcut(self, mock_run) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=json.dumps({"code": 0}),
            stderr="",
        )
        cli = LarkCLI(cli_path="lark-cli", timeout=10)
        cli.reply_text("om_123", "hello")

        command = mock_run.call_args.args[0]
        self.assertEqual(command[:3], ["lark-cli", "im", "+messages-reply"])
        self.assertIn("--message-id", command)
        self.assertIn("om_123", command)


class TestFeishuBotBehavior(unittest.TestCase):
    def test_text_message_uses_injected_conversation_service_with_feishu_scope(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            ai_client = FakeAIClient(response="legacy response")
            lark_cli = FakeLarkCLI()
            service = FakeConversationService(response="memory response")
            config = FeishuBotConfig(download_dir=temp_dir, log_dir=temp_dir)
            bot = build_bot_with_conversation_service(
                config,
                ai_client=ai_client,
                lark_cli=lark_cli,
                conversation_service=service,
            )

            bot._process_event(
                build_event(
                    "text",
                    {"text": "hello memory"},
                    sender_id="ou_sender_1",
                    chat_id="oc_chat_1",
                    chat_type="p2p",
                    message_id="om_text_1",
                )
            )

            self.assertEqual(lark_cli.replies[-1], ("om_text_1", "memory response"))
            self.assertEqual(ai_client.prompts, [])
            self.assertEqual(len(service.inputs), 1)
            chat_input = service.inputs[-1]
            self.assertEqual(chat_input.message, "hello memory")
            self.assertEqual(chat_input.source_message_id, "om_text_1")
            self.assertIsInstance(chat_input.scope, MemoryScope)
            self.assertEqual(chat_input.scope.app, "feishu_bot")
            self.assertEqual(chat_input.scope.channel, "feishu")
            self.assertEqual(chat_input.scope.user_id, "ou_sender_1")
            self.assertEqual(chat_input.scope.conversation_id, "oc_chat_1")
            self.assertEqual(chat_input.scope.thread_id, "oc_chat_1")
            self.assertEqual(chat_input.scope.key(), ("feishu_bot", "feishu", "ou_sender_1", "oc_chat_1", "oc_chat_1"))
            self.assertEqual(chat_input.scope.metadata.get("chat_type"), "p2p")

    def test_default_memory_store_is_in_memory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bot = FeishuBot(
                FeishuBotConfig(download_dir=temp_dir, log_dir=temp_dir),
                ai_client=FakeAIClient(),
                lark_cli=FakeLarkCLI(),
            )

            self.assertIsInstance(bot.conversation_service.store, InMemoryMemoryStore)

    def test_sqlite_memory_store_can_be_configured(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = str(Path(temp_dir) / "memory.sqlite3")
            bot = FeishuBot(
                FeishuBotConfig(
                    download_dir=temp_dir,
                    log_dir=temp_dir,
                    memory_store="sqlite",
                    memory_db_path=db_path,
                    memory_busy_timeout_ms=2468,
                ),
                ai_client=FakeAIClient(),
                lark_cli=FakeLarkCLI(),
            )
            try:
                store = bot.conversation_service.store
                self.assertIsInstance(store, SQLiteMemoryStore)
                self.assertEqual(store.db_path, db_path)
                self.assertEqual(store.busy_timeout_ms, 2468)
            finally:
                bot.conversation_service.store.close()

    def test_sqlite_memory_store_recovers_duplicate_after_bot_reopen(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = str(Path(temp_dir) / "memory.sqlite3")
            config = FeishuBotConfig(
                download_dir=temp_dir,
                log_dir=temp_dir,
                memory_store="sqlite",
                memory_db_path=db_path,
            )
            first_ai = FakeAIClient(response="first answer")
            first_lark = FakeLarkCLI()
            first_bot = FeishuBot(config, ai_client=first_ai, lark_cli=first_lark)
            first_bot._process_event(build_event("text", {"text": "hello"}, message_id="same_message"))
            first_bot.conversation_service.store.close()

            second_ai = FakeAIClient(response="second answer")
            second_lark = FakeLarkCLI()
            second_bot = FeishuBot(config, ai_client=second_ai, lark_cli=second_lark)
            try:
                second_bot._process_event(build_event("text", {"text": "hello"}, message_id="same_message"))
            finally:
                second_bot.conversation_service.store.close()

            self.assertEqual(first_lark.replies[-1], ("same_message", "first answer"))
            self.assertEqual(second_lark.replies[-1], ("same_message", "first answer"))
            self.assertEqual(first_ai.prompts, ["Current user message:\nhello"])
            self.assertEqual(second_ai.prompts, [])

    def test_sqlite_memory_cleanup_on_start_runs_retention_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = str(Path(temp_dir) / "memory.sqlite3")
            old_scope = MemoryScope(
                app="feishu_bot",
                channel="feishu",
                user_id="ou_old",
                conversation_id="oc_old",
                thread_id="oc_old",
            )
            fresh_scope = MemoryScope(
                app="feishu_bot",
                channel="feishu",
                user_id="ou_fresh",
                conversation_id="oc_fresh",
                thread_id="oc_fresh",
            )
            store = SQLiteMemoryStore(db_path)
            store.append_user_turn(
                ConversationTurn(
                    turn_id="old_user",
                    scope=old_scope,
                    role="user",
                    content="old",
                    status=TurnStatus.ACCEPTED,
                    source_message_id="old_msg",
                )
            )
            store.append_assistant_turn(
                ConversationTurn(
                    turn_id="old_assistant",
                    scope=old_scope,
                    role="assistant",
                    content="old answer",
                    status=TurnStatus.DELIVERED,
                    parent_turn_id="old_user",
                    request_message_id="old_msg",
                )
            )
            store.set_summary(old_scope, "old summary")
            store.add_fact(old_scope, "old fact")
            store.append_user_turn(
                ConversationTurn(
                    turn_id="fresh_user",
                    scope=fresh_scope,
                    role="user",
                    content="fresh",
                    status=TurnStatus.ACCEPTED,
                    source_message_id="fresh_msg",
                )
            )

            old_text = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat(timespec="microseconds")
            with store._lock, store._conn:
                store._conn.execute("UPDATE conversation_turns SET created_at = ? WHERE thread_id = ?", (old_text, "oc_old"))
                store._conn.execute(
                    "UPDATE conversation_summaries SET updated_at = ? WHERE thread_id = ?",
                    (old_text, "oc_old"),
                )
                store._conn.execute(
                    "UPDATE memory_facts SET created_at = ? WHERE thread_id = ?",
                    (old_text, "oc_old"),
                )
            store.close()

            bot = FeishuBot(
                FeishuBotConfig(
                    download_dir=temp_dir,
                    log_dir=temp_dir,
                    memory_store="sqlite",
                    memory_db_path=db_path,
                    memory_cleanup_on_start=True,
                    memory_retention_days=7,
                ),
                ai_client=FakeAIClient(),
                lark_cli=FakeLarkCLI(),
            )
            try:
                self.assertEqual(bot.metrics["memory_cleanup_deleted"], 4)
                self.assertEqual(list(bot.conversation_service.store.get_recent_turns(old_scope, limit=10)), [])
                self.assertEqual(bot.conversation_service.store.get_summary(old_scope), "")
                self.assertEqual(list(bot.conversation_service.store.get_facts(old_scope, limit=10)), [])
                self.assertEqual(
                    [turn.turn_id for turn in bot.conversation_service.store.get_recent_turns(fresh_scope, limit=10)],
                    ["fresh_user"],
                )
            finally:
                bot.conversation_service.store.close()

    def test_auto_summary_can_be_enabled_by_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            ai_client = FakeAIClient(response="自动摘要")
            bot = FeishuBot(
                FeishuBotConfig(
                    download_dir=temp_dir,
                    log_dir=temp_dir,
                    memory_enable_auto_summary=True,
                    memory_summary_after_turns=2,
                    memory_summary_refresh_turns=2,
                ),
                ai_client=ai_client,
                lark_cli=FakeLarkCLI(),
            )

            bot._process_event(build_event("text", {"text": "hello"}, message_id="summary_message"))

            message = bot._extract_message_info(
                build_event("text", {"text": "hello"}, message_id="summary_message")
            )
            assert message is not None
            scope = bot._memory_scope(message)
            self.assertEqual(bot.conversation_service.get_summary(scope), "自动摘要")
            self.assertEqual(len(ai_client.prompts), 2)
            self.assertIn("Current user message:\nhello", ai_client.prompts[0])
            self.assertIn("请用中文为下面对话生成简洁摘要", ai_client.prompts[1])

    def test_explicit_fact_extraction_can_be_enabled_by_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bot = FeishuBot(
                FeishuBotConfig(
                    download_dir=temp_dir,
                    log_dir=temp_dir,
                    memory_enable_fact_extraction=True,
                ),
                ai_client=FakeAIClient(response="ok"),
                lark_cli=FakeLarkCLI(),
            )

            event = build_event("text", {"text": "记住：用户偏好中文 token=secret"}, message_id="fact_message")
            bot._process_event(event)

            message = bot._extract_message_info(event)
            assert message is not None
            facts = bot.conversation_service.store.get_facts(bot._memory_scope(message), 5)
            self.assertEqual(list(facts), ["用户偏好中文 token=[REDACTED]"])

    def test_pending_file_is_scoped_by_chat_for_same_user(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            ai_client = FakeAIClient(response="legacy response")
            lark_cli = FakeLarkCLI()
            service = FakeConversationService(response="memory response")
            config = FeishuBotConfig(download_dir=temp_dir, log_dir=temp_dir, allow_group_chats=True)
            bot = build_bot_with_conversation_service(
                config,
                ai_client=ai_client,
                lark_cli=lark_cli,
                conversation_service=service,
            )

            bot._process_event(
                build_event(
                    "file",
                    {"file_key": "file_a", "file_name": "notes.txt"},
                    sender_id="ou_same_user",
                    chat_id="oc_chat_a",
                    message_id="om_file_a",
                )
            )
            bot._process_event(
                build_event(
                    "text",
                    {"text": "summarize this chat"},
                    sender_id="ou_same_user",
                    chat_id="oc_chat_b",
                    message_id="om_text_b",
                )
            )
            bot._process_event(
                build_event(
                    "text",
                    {"text": "now analyze the file"},
                    sender_id="ou_same_user",
                    chat_id="oc_chat_a",
                    message_id="om_text_a",
                )
            )

            self.assertEqual(len(service.inputs), 2)
            other_chat_input = service.inputs[0]
            original_chat_input = service.inputs[1]
            self.assertEqual(other_chat_input.scope.conversation_id, "oc_chat_b")
            self.assertEqual(other_chat_input.message, "summarize this chat")
            self.assertNotIn("notes.txt", other_chat_input.message)
            self.assertNotIn("hello world", other_chat_input.message)
            self.assertEqual(original_chat_input.scope.conversation_id, "oc_chat_a")
            self.assertIn("notes.txt", original_chat_input.message)
            self.assertIn("hello world", original_chat_input.message)
            self.assertIn("now analyze the file", original_chat_input.message)

    def test_successful_reply_marks_assistant_delivered_when_supported(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = FakeConversationService(response="memory response", assistant_turn_id="assistant_success")
            bot = build_bot_with_conversation_service(
                FeishuBotConfig(download_dir=temp_dir, log_dir=temp_dir),
                ai_client=FakeAIClient(response="legacy response"),
                lark_cli=FakeLarkCLI(),
                conversation_service=service,
            )

            bot._process_event(build_event("text", {"text": "hello"}, message_id="om_success"))

            self.assertEqual(service.delivered, ["assistant_success"])
            self.assertEqual(service.failed, [])

    def test_failed_reply_marks_assistant_failed_when_supported(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = FakeConversationService(response="memory response", assistant_turn_id="assistant_failed")
            bot = build_bot_with_conversation_service(
                FeishuBotConfig(download_dir=temp_dir, log_dir=temp_dir),
                ai_client=FakeAIClient(response="legacy response"),
                lark_cli=FakeLarkCLI(fail_replies=True),
                conversation_service=service,
            )

            bot._process_event(build_event("text", {"text": "hello"}, message_id="om_failure"))

            self.assertEqual(service.delivered, [])
            self.assertEqual(service.failed, ["assistant_failed"])

    def test_reset_command_clears_scope_memory_and_pending_file_without_calling_ai(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = FakeConversationService()
            context = SessionContextManager(default_ttl=300)
            context.set_pending_file(
                feishu_context_key(),
                FileInfo(file_path="/tmp/a.py", file_name="a.py", file_kind=".py", file_content="print('hi')"),
            )
            bot = build_bot_with_conversation_service(
                FeishuBotConfig(download_dir=temp_dir, log_dir=temp_dir),
                ai_client=FakeAIClient(response="legacy response"),
                lark_cli=FakeLarkCLI(),
                conversation_service=service,
                context_manager=context,
            )

            bot._process_event(build_event("text", {"text": "/reset"}))

            self.assertEqual(bot.lark_cli.replies[-1], ("om_message_1", "已重置当前会话记忆。"))
            self.assertEqual(service.inputs, [])
            self.assertEqual(len(service.reset_scopes), 1)
            self.assertEqual(service.reset_scopes[0].key(), feishu_scope_key())
            self.assertIsNone(context.get_pending_file(feishu_context_key()))

    def test_summary_command_replies_current_summary_without_calling_ai(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = FakeConversationService()
            service.summary = "当前摘要"
            lark_cli = FakeLarkCLI()
            bot = build_bot_with_conversation_service(
                FeishuBotConfig(download_dir=temp_dir, log_dir=temp_dir),
                ai_client=FakeAIClient(response="legacy response"),
                lark_cli=lark_cli,
                conversation_service=service,
            )

            bot._process_event(build_event("text", {"text": "/summary"}))

            self.assertEqual(lark_cli.replies[-1], ("om_message_1", "当前摘要"))
            self.assertEqual(service.inputs, [])

    def test_summary_command_handles_empty_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = FakeConversationService()
            lark_cli = FakeLarkCLI()
            bot = build_bot_with_conversation_service(
                FeishuBotConfig(download_dir=temp_dir, log_dir=temp_dir),
                ai_client=FakeAIClient(response="legacy response"),
                lark_cli=lark_cli,
                conversation_service=service,
            )

            bot._process_event(build_event("text", {"text": "/summary"}))

            self.assertEqual(lark_cli.replies[-1], ("om_message_1", "当前会话暂无摘要。"))
            self.assertEqual(service.inputs, [])

    def test_memory_off_and_on_control_next_message_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = FakeConversationService(response="memory response")
            lark_cli = FakeLarkCLI()
            bot = build_bot_with_conversation_service(
                FeishuBotConfig(download_dir=temp_dir, log_dir=temp_dir),
                ai_client=FakeAIClient(response="legacy response"),
                lark_cli=lark_cli,
                conversation_service=service,
            )

            bot._process_event(build_event("text", {"text": "/memory off"}, message_id="m_off"))
            bot._process_event(build_event("text", {"text": "hello"}, message_id="m_text_off"))
            bot._process_event(build_event("text", {"text": "/memory on"}, message_id="m_on"))
            bot._process_event(build_event("text", {"text": "hello again"}, message_id="m_text_on"))

            self.assertEqual(lark_cli.replies[0], ("m_off", "已关闭当前会话记忆。"))
            self.assertEqual(lark_cli.replies[2], ("m_on", "已开启当前会话记忆。"))
            self.assertEqual(service.inputs[0].memory_mode, MemoryMode.OFF)
            self.assertEqual(service.inputs[1].memory_mode, MemoryMode.ON)

    def test_global_memory_disabled_forces_off_and_blocks_memory_on(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = FakeConversationService(response="memory response")
            lark_cli = FakeLarkCLI()
            bot = build_bot_with_conversation_service(
                FeishuBotConfig(download_dir=temp_dir, log_dir=temp_dir, memory_enabled=False),
                ai_client=FakeAIClient(response="legacy response"),
                lark_cli=lark_cli,
                conversation_service=service,
            )

            bot._process_event(build_event("text", {"text": "before override"}, message_id="m_text_before"))
            bot._process_event(build_event("text", {"text": "/memory on"}, message_id="m_on"))
            bot._process_event(build_event("text", {"text": "after override"}, message_id="m_text_after"))

            self.assertEqual(lark_cli.replies[1], ("m_on", "当前会话记忆已被灰度开关关闭。"))
            self.assertEqual(
                [chat_input.memory_mode for chat_input in service.inputs],
                [MemoryMode.OFF, MemoryMode.OFF],
            )

    def test_conversation_log_redacts_sensitive_values_and_includes_trace(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bot = FeishuBot(
                FeishuBotConfig(download_dir=temp_dir, log_dir=temp_dir),
                ai_client=FakeAIClient(response="token=response-secret"),
                lark_cli=FakeLarkCLI(),
            )

            bot._process_event(
                build_event(
                    "text",
                    {"text": "password=user-secret api_key=user-key authorization: bearer user-token"},
                    message_id="m_secret",
                )
            )

            log_files = sorted(Path(temp_dir).glob("*.jsonl"))
            self.assertEqual(len(log_files), 1)
            log_entry = json.loads(log_files[0].read_text(encoding="utf-8").splitlines()[-1])
            self.assertEqual(
                log_entry["user_message"],
                "password=[REDACTED] api_key=[REDACTED] authorization: bearer [REDACTED]",
            )
            self.assertEqual(log_entry["ai_response"], "token=[REDACTED]")
            serialized_log = json.dumps(log_entry, ensure_ascii=False)
            self.assertNotIn("user-secret", serialized_log)
            self.assertNotIn("user-key", serialized_log)
            self.assertNotIn("user-token", serialized_log)
            self.assertNotIn("response-secret", serialized_log)
            self.assertEqual(log_entry["trace"]["memory_mode"], "on")
            self.assertTrue(log_entry["trace"]["memory_enabled"])
            self.assertEqual(log_entry["trace"]["scope"]["thread_id"], "oc_chat_1")

    def test_conversation_logger_redacts_sensitive_values_inside_trace(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = ConversationLogger(log_dir=temp_dir)

            logger.log_conversation(
                user_id="ou_test",
                user_message="hello",
                ai_response="ok",
                message_id="m_trace_secret",
                trace={
                    "metadata": {
                        "token": "token=trace-secret",
                        "headers": ["authorization: bearer trace-token"],
                    }
                },
                redact=True,
            )

            log_files = sorted(Path(temp_dir).glob("*.jsonl"))
            self.assertEqual(len(log_files), 1)
            log_entry = json.loads(log_files[0].read_text(encoding="utf-8").splitlines()[-1])
            serialized_log = json.dumps(log_entry, ensure_ascii=False)
            self.assertIn("token=[REDACTED]", serialized_log)
            self.assertIn("authorization: bearer [REDACTED]", serialized_log)
            self.assertNotIn("trace-secret", serialized_log)
            self.assertNotIn("trace-token", serialized_log)

    def test_conversation_log_can_disable_redaction_and_trace(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bot = FeishuBot(
                FeishuBotConfig(
                    download_dir=temp_dir,
                    log_dir=temp_dir,
                    memory_log_redaction=False,
                    memory_trace_enabled=False,
                ),
                ai_client=FakeAIClient(response="token=response-secret"),
                lark_cli=FakeLarkCLI(),
            )

            bot._process_event(
                build_event(
                    "text",
                    {"text": "password=user-secret"},
                    message_id="m_secret_unredacted",
                )
            )

            log_files = sorted(Path(temp_dir).glob("*.jsonl"))
            self.assertEqual(len(log_files), 1)
            log_entry = json.loads(log_files[0].read_text(encoding="utf-8").splitlines()[-1])
            self.assertEqual(log_entry["user_message"], "password=user-secret")
            self.assertEqual(log_entry["ai_response"], "token=response-secret")
            self.assertNotIn("trace", log_entry)

    def test_metrics_count_text_command_ai_error_and_reply_failure(self) -> None:
        class BrokenConversationService(FakeConversationService):
            def chat(self, chat_input: ChatInput) -> ChatOutput:
                raise RuntimeError("backend down")

        with tempfile.TemporaryDirectory() as temp_dir:
            normal_bot = build_bot_with_conversation_service(
                FeishuBotConfig(download_dir=temp_dir, log_dir=temp_dir),
                ai_client=FakeAIClient(response="legacy response"),
                lark_cli=FakeLarkCLI(),
                conversation_service=FakeConversationService(response="ok"),
            )
            normal_bot._process_event(build_event("text", {"text": "hello"}, message_id="m_normal"))

            self.assertEqual(normal_bot.metrics["text_messages"], 1)
            self.assertEqual(normal_bot.metrics["memory_commands"], 0)
            self.assertEqual(normal_bot.metrics["ai_errors"], 0)
            self.assertEqual(normal_bot.metrics["reply_failures"], 0)

            service = BrokenConversationService()
            bot = build_bot_with_conversation_service(
                FeishuBotConfig(download_dir=temp_dir, log_dir=temp_dir),
                ai_client=FakeAIClient(response="legacy response"),
                lark_cli=FakeLarkCLI(fail_replies=True),
                conversation_service=service,
            )

            bot._process_event(build_event("text", {"text": "/summary"}, message_id="m_command"))
            bot._process_event(build_event("text", {"text": "hello"}, message_id="m_error"))

            self.assertEqual(bot.metrics["text_messages"], 2)
            self.assertEqual(bot.metrics["memory_commands"], 1)
            self.assertEqual(bot.metrics["ai_errors"], 1)
            self.assertEqual(bot.metrics["reply_failures"], 1)

    def test_text_message_consumes_pending_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            ai_client = FakeAIClient(response="analysis")
            lark_cli = FakeLarkCLI()
            config = FeishuBotConfig(download_dir=temp_dir, log_dir=temp_dir)
            context = SessionContextManager(default_ttl=300)
            context_key = feishu_context_key()
            context.set_pending_file(
                context_key,
                FileInfo(file_path="/tmp/a.py", file_name="a.py", file_kind=".py", file_content="print('hi')"),
            )
            bot = FeishuBot(
                config,
                ai_client=ai_client,
                lark_cli=lark_cli,
                context_manager=context,
            )

            bot._process_event(build_event("text", {"text": "帮我分析"}))

            self.assertEqual(lark_cli.replies[-1], ("om_message_1", "analysis"))
            self.assertIn("用户上传了一个文件：a.py", ai_client.prompts[-1])
            self.assertIsNone(context.get_pending_file(context_key))

    def test_file_message_downloads_and_waits_for_followup(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            ai_client = FakeAIClient()
            lark_cli = FakeLarkCLI()
            config = FeishuBotConfig(download_dir=temp_dir, log_dir=temp_dir)
            context = SessionContextManager(default_ttl=300)
            bot = FeishuBot(
                config,
                ai_client=ai_client,
                lark_cli=lark_cli,
                context_manager=context,
            )

            bot._process_event(build_event("file", {"file_key": "file_123", "file_name": "demo.txt"}))

            pending = context.get_pending_file(feishu_context_key())
            self.assertIsNotNone(pending)
            assert pending is not None
            self.assertEqual(pending.file_content, "hello world")
            self.assertIn("已收到文件：demo.txt", lark_cli.replies[-1][1])

    def test_group_chat_is_ignored_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            ai_client = FakeAIClient()
            lark_cli = FakeLarkCLI()
            config = FeishuBotConfig(download_dir=temp_dir, log_dir=temp_dir)
            bot = FeishuBot(config, ai_client=ai_client, lark_cli=lark_cli)

            bot._process_event(build_event("text", {"text": "hello"}, chat_type="group"))

            self.assertEqual(lark_cli.replies, [])
            self.assertEqual(ai_client.prompts, [])

    def test_special_file_names_are_supported(self) -> None:
        self.assertEqual(FeishuBot._resolve_file_kind(".env"), ".env")
        self.assertEqual(FeishuBot._resolve_file_kind("Dockerfile"), ".dockerfile")
        self.assertEqual(FeishuBot._resolve_file_kind("Makefile"), ".makefile")

    def test_non_message_event_is_ignored(self) -> None:
        bot = FeishuBot(FeishuBotConfig(), ai_client=FakeAIClient(), lark_cli=FakeLarkCLI())
        bot._process_event({"schema": "2.0", "header": {"event_type": "contact.user.created_v3"}, "event": {}})


if __name__ == "__main__":
    unittest.main()
