# -*- coding: utf-8 -*-
"""Feishu bot driven primarily by lark-cli."""

from __future__ import annotations

import json
import os
import queue
import threading
from typing import Any

from loguru import logger

from products.feishu_bot.config import FeishuBotConfig
from products.feishu_bot.file_flow import (
    FeishuFileFlow,
    build_file_prompt,
    extract_file_info,
    read_file_content,
    relative_download_path,
    resolve_file_kind,
    safe_file_name,
)
from products.feishu_bot.handlers.context import FileInfo, SessionContextManager
from products.feishu_bot.lark_cli import LarkCLI, LarkCLIError
from products.feishu_bot.logging import ConversationLogger
from products.feishu_bot.memory_adapter import (
    FeishuMemoryAdapter,
    extract_explicit_facts,
    summarize_memory,
)
from products.feishu_bot.message_parser import MessageEnvelope, extract_message_info, extract_text
from runtime.factory import get_client
from runtime.memory import (
    ChatInput,
    ConversationService,
    MemoryMode,
    MemoryScope,
)


class FeishuBot:
    """A Feishu bot that uses lark-cli for events, replies, and downloads."""

    def __init__(
        self,
        config: FeishuBotConfig,
        *,
        ai_client: Any | None = None,
        lark_cli: LarkCLI | None = None,
        conversation_logger: ConversationLogger | None = None,
        context_manager: SessionContextManager | None = None,
        conversation_service: ConversationService | None = None,
    ) -> None:
        self.config = config
        if ai_client is not None:
            self.ai_client = ai_client
        elif conversation_service is not None and hasattr(conversation_service, "ai_client"):
            self.ai_client = conversation_service.ai_client
        else:
            self.ai_client = self._create_ai_client(config)
        self.lark_cli = lark_cli or LarkCLI(cli_path=config.lark_cli_path, timeout=config.timeout)
        self.conversation_logger = conversation_logger or ConversationLogger(log_dir=config.log_dir)
        self.context_manager = context_manager or SessionContextManager(default_ttl=config.session_ttl)
        self.metrics: dict[str, int] = {
            "text_messages": 0,
            "memory_commands": 0,
            "ai_errors": 0,
            "reply_successes": 0,
            "reply_failures": 0,
            "reused_responses": 0,
            "memory_cleanup_deleted": 0,
        }
        self.memory_adapter = FeishuMemoryAdapter(
            config=config,
            ai_client=self.ai_client,
            metrics=self.metrics,
            summarizer=self._summarize_memory,
            fact_extractor=self._extract_explicit_facts,
            conversation_service=conversation_service,
        )
        self.conversation_service = self.memory_adapter.conversation_service
        self.file_flow = FeishuFileFlow(
            download_dir=config.download_dir,
            lark_cli=self.lark_cli,
            context_manager=self.context_manager,
            context_key=self._context_key,
            reply_text=self._safe_reply,
            log_conversation=self.conversation_logger.log_conversation,
            trace_builder=self._memory_trace,
            trace_enabled=config.memory_trace_enabled,
            log_redaction=config.memory_log_redaction,
        )
        self.subscription_process: Any | None = None

        self._event_queue: queue.Queue[dict[str, Any] | None] = queue.Queue(maxsize=max(config.worker_queue_size, 1))
        self._worker = threading.Thread(target=self._worker_loop, name="feishu-bot-worker", daemon=True)
        self._worker_started = False

        os.makedirs(config.download_dir, exist_ok=True)

    @staticmethod
    def _create_ai_client(config: FeishuBotConfig) -> Any:
        if config.backend == "trae":
            return get_client(
                backend="trae",
                trae_cli_path=config.trae_cli_path,
                model=config.model,
                agent=config.agent,
                timeout=config.timeout,
                yolo=True,
            )
        return get_client(backend=config.backend, timeout=config.timeout)

    def start(self) -> None:
        self.lark_cli.ensure_available()
        cli_config = self.lark_cli.show_config()
        logger.info(f"lark-cli 已就绪: app_id={cli_config.get('appId', 'unknown')}")

        self._ensure_worker()
        self.subscription_process = self.lark_cli.subscribe_events(event_types=self.config.event_types)
        assert self.subscription_process.stdout is not None

        for line in self.subscription_process.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                logger.debug(f"忽略非 JSON 事件行: {line[:200]}")
                continue

            try:
                self._event_queue.put(event, timeout=1)
            except queue.Full:
                logger.error("消息队列已满，丢弃一条飞书事件。")

        return_code = self.subscription_process.wait()
        if return_code != 0:
            stderr = ""
            if self.subscription_process.stderr is not None:
                stderr = self.subscription_process.stderr.read().strip()
            raise RuntimeError(f"lark-cli event 订阅异常退出: code={return_code}, stderr={stderr}")

    def stop(self) -> None:
        if self.subscription_process and self.subscription_process.poll() is None:
            self.subscription_process.terminate()
        if self._worker_started:
            self._event_queue.put(None)
            self._worker.join(timeout=2)
            self._worker_started = False

    def _ensure_worker(self) -> None:
        if not self._worker_started:
            self._worker.start()
            self._worker_started = True

    def _worker_loop(self) -> None:
        while True:
            event = self._event_queue.get()
            if event is None:
                return
            try:
                self._process_event(event)
            except Exception as exc:
                logger.exception(f"处理飞书消息失败: {exc}")

    def _process_event(self, payload: dict[str, Any]) -> None:
        envelope = self._extract_message_info(payload)
        if envelope is None:
            return

        if envelope.sender_type == "bot":
            logger.debug("忽略 bot 自己发出的消息。")
            return

        if envelope.chat_type != "p2p" and not self.config.allow_group_chats:
            logger.info(f"忽略非 P2P 会话消息: chat_type={envelope.chat_type}, chat_id={envelope.chat_id}")
            return

        if envelope.message_type == "text":
            self._handle_text_message(envelope)
            return

        if envelope.message_type == "file":
            self._handle_file_message(envelope)
            return

        self._safe_reply(envelope.message_id, "目前只支持文本消息和文件消息。")

    def _extract_message_info(self, payload: dict[str, Any]) -> MessageEnvelope | None:
        return extract_message_info(payload)

    def _handle_text_message(self, message: MessageEnvelope) -> None:
        user_message = self._extract_text(message.content)
        if not user_message:
            logger.warning("收到空文本消息，忽略。")
            return

        self._increment_metric("text_messages")
        scope = self._memory_scope(message)
        command_response = self._handle_memory_command(scope, user_message)
        if command_response is not None:
            self._increment_metric("memory_commands")
            self._safe_reply(message.message_id, command_response)
            self.conversation_logger.log_conversation(
                user_id=message.sender_id,
                user_message=user_message,
                ai_response=command_response,
                message_id=message.message_id,
                trace=self._memory_trace(scope=scope, command=user_message) if self.config.memory_trace_enabled else None,
                redact=self.config.memory_log_redaction,
            )
            return

        pending_file = self.context_manager.pop_pending_file(self._context_key(scope))
        if pending_file:
            service_message = self._build_file_prompt(pending_file, user_message)
            user_log = f"[文件:{pending_file.file_name}] {user_message}"
        else:
            service_message = user_message
            user_log = user_message

        try:
            output = self.conversation_service.chat(
                ChatInput(
                    scope=scope,
                    message=service_message,
                    source_message_id=message.message_id,
                    memory_mode=self._memory_mode(scope),
                    metadata={
                        "chat_type": message.chat_type,
                        "event_type": message.event_type,
                        "message_type": message.message_type,
                    },
                )
            )
            ai_response = output.response
        except Exception as exc:
            self._increment_metric("ai_errors")
            logger.error(f"AI 响应失败: {exc}")
            ai_response = f"抱歉，AI 服务暂时不可用: {exc}"
            output = None

        if not ai_response:
            logger.info(f"跳过重复或正在处理的消息: message_id={message.message_id}")
            return

        delivered = self._safe_reply(message.message_id, ai_response)
        if delivered:
            self._increment_metric("reply_successes")
        else:
            self._increment_metric("reply_failures")
        if (
            output is not None
            and output.assistant_turn is not None
            and output.assistant_turn.turn_id
            and not output.reused_response
        ):
            self._mark_assistant_delivery(output.assistant_turn.turn_id, delivered)
        if output is not None and output.reused_response:
            self._increment_metric("reused_responses")

        self.conversation_logger.log_conversation(
            user_id=message.sender_id,
            user_message=user_log,
            ai_response=ai_response,
            message_id=message.message_id,
            trace=self._output_trace(scope, output, delivered) if self.config.memory_trace_enabled else None,
            redact=self.config.memory_log_redaction,
        )

    def _handle_file_message(self, message: MessageEnvelope) -> None:
        scope = self._memory_scope(message)
        self.file_flow.handle_file_message(
            message_id=message.message_id,
            sender_id=message.sender_id,
            content=message.content,
            scope=scope,
        )

    def _safe_reply(self, message_id: str, content: str) -> bool:
        try:
            self.lark_cli.reply_text(message_id, content)
            return True
        except LarkCLIError as exc:
            logger.error(f"通过 lark-cli 回复消息失败: {exc}")
            return False

    def _mark_assistant_delivery(self, assistant_turn_id: str, delivered: bool) -> None:
        try:
            if delivered:
                self.conversation_service.mark_assistant_delivered(assistant_turn_id)
            else:
                self.conversation_service.mark_assistant_failed(assistant_turn_id)
        except Exception as exc:
            logger.error(f"更新助手消息投递状态失败: {exc}")

    def _handle_memory_command(self, scope: MemoryScope, user_message: str) -> str | None:
        return self.memory_adapter.handle_command(
            scope=scope,
            user_message=user_message,
            clear_pending_file=self.context_manager.clear_pending_file,
        )

    def _memory_mode(self, scope: MemoryScope) -> MemoryMode:
        return self.memory_adapter.memory_mode(scope)

    def _output_trace(self, scope: MemoryScope, output: Any | None, delivered: bool) -> dict[str, Any]:
        trace = self._memory_trace(scope=scope, delivered=delivered)
        if output is None:
            trace["assistant_turn_id"] = None
            return trace
        trace.update(
            {
                "duplicate": output.duplicate,
                "reused_response": output.reused_response,
                "assistant_turn_id": output.assistant_turn.turn_id if output.assistant_turn else None,
                "metadata": output.metadata,
            }
        )
        return trace

    def _memory_trace(self, *, scope: MemoryScope, **extra: Any) -> dict[str, Any]:
        trace = {
            "scope": {
                "app": scope.app,
                "channel": scope.channel,
                "user_id": scope.user_id,
                "conversation_id": scope.conversation_id,
                "thread_id": scope.thread_id,
            },
            "memory_mode": self._memory_mode(scope).value,
            "memory_enabled": self.config.memory_enabled,
        }
        trace.update(extra)
        return trace

    def _increment_metric(self, name: str) -> None:
        self.metrics[name] = self.metrics.get(name, 0) + 1

    def get_metrics(self) -> dict[str, int]:
        return dict(self.metrics)

    def _summarize_memory(self, conversation_text: str) -> str:
        return summarize_memory(self.ai_client, conversation_text)

    @staticmethod
    def _extract_explicit_facts(conversation_text: str) -> list[str]:
        return extract_explicit_facts(conversation_text)

    def _relative_download_path(self, message_id: str, file_name: str) -> str:
        return relative_download_path(self.config.download_dir, message_id, file_name)

    @staticmethod
    def _safe_file_name(file_name: str) -> str:
        return safe_file_name(file_name)

    @staticmethod
    def _extract_text(content: str) -> str:
        return extract_text(content)

    @staticmethod
    def _extract_file_info(content: str) -> dict[str, Any]:
        return extract_file_info(content)

    @staticmethod
    def _resolve_file_kind(file_name: str) -> str:
        return resolve_file_kind(file_name)

    @staticmethod
    def _build_file_prompt(file_info: FileInfo, user_message: str) -> str:
        return build_file_prompt(file_info, user_message)

    @staticmethod
    def _read_file_content(file_path: str, max_size: int = 100000) -> str:
        return read_file_content(file_path, max_size=max_size)

    def _memory_scope(self, message: MessageEnvelope) -> MemoryScope:
        return self.memory_adapter.create_scope(
            sender_id=message.sender_id,
            chat_id=message.chat_id,
            chat_type=message.chat_type,
            event_type=message.event_type,
        )

    @staticmethod
    def _context_key(scope: MemoryScope) -> str:
        return FeishuMemoryAdapter.context_key(scope)
