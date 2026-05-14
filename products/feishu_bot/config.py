# -*- coding: utf-8 -*-
"""Feishu bot configuration."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

from loguru import logger


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _normalize_memory_store(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_")
    if normalized in {"memory", "inmemory"}:
        return "in_memory"
    return normalized


@dataclass
class FeishuBotConfig:
    """Configuration for the lark-cli based Feishu bot."""

    app_id: str = ""
    app_secret: str = ""

    backend: str = "codex"
    model: str = "GLM-5"
    agent: str = ""
    trae_cli_path: str = "trae-cli"
    timeout: int = 120

    lark_cli_path: str = "lark-cli"
    log_dir: str = "logs/conversations"
    download_dir: str = "downloads"
    session_ttl: int = 300
    allow_group_chats: bool = False
    worker_queue_size: int = 100
    event_types: str = "im.message.receive_v1"
    memory_store: str = "in_memory"
    memory_db_path: str = "data/feishu_bot_memory.sqlite3"
    memory_busy_timeout_ms: int = 5000
    memory_recent_turn_limit: int = 8
    memory_summary_after_turns: int = 12
    memory_summary_refresh_turns: int = 6
    memory_enable_auto_summary: bool = False
    memory_enable_fact_extraction: bool = False
    memory_enable_sensitive_filter: bool = True
    memory_enabled: bool = True
    memory_retention_days: int = 0
    memory_cleanup_on_start: bool = False
    memory_log_redaction: bool = True
    memory_trace_enabled: bool = True

    def __post_init__(self) -> None:
        self.app_id = os.environ.get("FEISHU_APP_ID", self.app_id)
        self.app_secret = os.environ.get("FEISHU_APP_SECRET", self.app_secret)
        self.backend = os.environ.get("FEISHU_BACKEND", self.backend)
        if os.environ.get("FEISHU_USE_CLAUDE", "").lower() == "true":
            self.backend = "claude_code"
        self.model = os.environ.get("FEISHU_MODEL", self.model)
        self.agent = os.environ.get("FEISHU_AGENT", self.agent)
        self.trae_cli_path = os.environ.get("TRAE_CLI_PATH", self.trae_cli_path)
        self.timeout = int(os.environ.get("FEISHU_TIMEOUT", str(self.timeout)))
        self.lark_cli_path = os.environ.get("LARK_CLI_PATH", self.lark_cli_path)
        self.log_dir = os.environ.get("FEISHU_LOG_DIR", self.log_dir)
        self.download_dir = os.environ.get("FEISHU_DOWNLOAD_DIR", self.download_dir)
        self.session_ttl = int(os.environ.get("FEISHU_SESSION_TTL", str(self.session_ttl)))
        self.allow_group_chats = _env_bool("FEISHU_ALLOW_GROUP_CHATS", self.allow_group_chats)
        self.worker_queue_size = int(os.environ.get("FEISHU_WORKER_QUEUE_SIZE", str(self.worker_queue_size)))
        self.event_types = os.environ.get("FEISHU_EVENT_TYPES", self.event_types)
        self.memory_store = _normalize_memory_store(os.environ.get("FEISHU_MEMORY_STORE", self.memory_store))
        self.memory_db_path = os.environ.get("FEISHU_MEMORY_DB_PATH", self.memory_db_path)
        self.memory_busy_timeout_ms = int(
            os.environ.get("FEISHU_MEMORY_BUSY_TIMEOUT_MS", str(self.memory_busy_timeout_ms))
        )
        self.memory_recent_turn_limit = int(
            os.environ.get("FEISHU_MEMORY_RECENT_TURN_LIMIT", str(self.memory_recent_turn_limit))
        )
        self.memory_summary_after_turns = int(
            os.environ.get("FEISHU_MEMORY_SUMMARY_AFTER_TURNS", str(self.memory_summary_after_turns))
        )
        self.memory_summary_refresh_turns = int(
            os.environ.get("FEISHU_MEMORY_SUMMARY_REFRESH_TURNS", str(self.memory_summary_refresh_turns))
        )
        self.memory_enable_auto_summary = _env_bool(
            "FEISHU_MEMORY_ENABLE_AUTO_SUMMARY",
            self.memory_enable_auto_summary,
        )
        self.memory_enable_fact_extraction = _env_bool(
            "FEISHU_MEMORY_ENABLE_FACT_EXTRACTION",
            self.memory_enable_fact_extraction,
        )
        self.memory_enable_sensitive_filter = _env_bool(
            "FEISHU_MEMORY_ENABLE_SENSITIVE_FILTER",
            self.memory_enable_sensitive_filter,
        )
        self.memory_enabled = _env_bool("FEISHU_MEMORY_ENABLED", self.memory_enabled)
        self.memory_retention_days = int(
            os.environ.get("FEISHU_MEMORY_RETENTION_DAYS", str(self.memory_retention_days))
        )
        self.memory_cleanup_on_start = _env_bool("FEISHU_MEMORY_CLEANUP_ON_START", self.memory_cleanup_on_start)
        self.memory_log_redaction = _env_bool("FEISHU_MEMORY_LOG_REDACTION", self.memory_log_redaction)
        self.memory_trace_enabled = _env_bool("FEISHU_MEMORY_TRACE_ENABLED", self.memory_trace_enabled)

    @classmethod
    def from_env(cls) -> "FeishuBotConfig":
        return cls()

    @classmethod
    def from_json(cls, file_path: str) -> "FeishuBotConfig":
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            logger.warning(f"配置文件不存在: {file_path}")
            return cls()
        except json.JSONDecodeError as e:
            logger.error(f"配置文件 JSON 解析失败: {e}")
            return cls()

        return cls(
            app_id=data.get("app_id", ""),
            app_secret=data.get("app_secret", ""),
            backend=data.get("backend", "codex"),
            model=data.get("model", "GLM-5"),
            agent=data.get("agent", ""),
            trae_cli_path=data.get("trae_cli_path", "trae-cli"),
            timeout=data.get("timeout", 120),
            lark_cli_path=data.get("lark_cli_path", "lark-cli"),
            log_dir=data.get("log_dir", "logs/conversations"),
            download_dir=data.get("download_dir", "downloads"),
            session_ttl=data.get("session_ttl", 300),
            allow_group_chats=bool(data.get("allow_group_chats", False)),
            worker_queue_size=data.get("worker_queue_size", 100),
            event_types=data.get("event_types", "im.message.receive_v1"),
            memory_store=data.get("memory_store", "in_memory"),
            memory_db_path=data.get("memory_db_path", "data/feishu_bot_memory.sqlite3"),
            memory_busy_timeout_ms=data.get("memory_busy_timeout_ms", 5000),
            memory_recent_turn_limit=data.get("memory_recent_turn_limit", 8),
            memory_summary_after_turns=data.get("memory_summary_after_turns", 12),
            memory_summary_refresh_turns=data.get("memory_summary_refresh_turns", 6),
            memory_enable_auto_summary=bool(data.get("memory_enable_auto_summary", False)),
            memory_enable_fact_extraction=bool(data.get("memory_enable_fact_extraction", False)),
            memory_enable_sensitive_filter=bool(data.get("memory_enable_sensitive_filter", True)),
            memory_enabled=bool(data.get("memory_enabled", True)),
            memory_retention_days=data.get("memory_retention_days", 0),
            memory_cleanup_on_start=bool(data.get("memory_cleanup_on_start", False)),
            memory_log_redaction=bool(data.get("memory_log_redaction", True)),
            memory_trace_enabled=bool(data.get("memory_trace_enabled", True)),
        )

    def validate(self) -> bool:
        if not self.lark_cli_path:
            logger.error("缺少必要配置: LARK_CLI_PATH")
            return False
        if self.memory_store not in {"in_memory", "sqlite"}:
            logger.error(f"不支持的记忆存储配置: {self.memory_store}")
            return False
        if self.memory_store == "sqlite" and not self.memory_db_path:
            logger.error("SQLite 记忆存储缺少必要配置: FEISHU_MEMORY_DB_PATH")
            return False
        if self.memory_retention_days < 0:
            logger.error("记忆保留天数不能小于 0: FEISHU_MEMORY_RETENTION_DAYS")
            return False
        return True

    def to_dict(self) -> dict:
        return {
            "app_id": self.app_id[:8] + "***" if len(self.app_id) > 8 else "***",
            "app_secret": "***",
            "backend": self.backend,
            "model": self.model,
            "lark_cli_path": self.lark_cli_path,
            "log_dir": self.log_dir,
            "download_dir": self.download_dir,
            "session_ttl": self.session_ttl,
            "allow_group_chats": self.allow_group_chats,
            "event_types": self.event_types,
            "memory_store": self.memory_store,
            "memory_db_path": self.memory_db_path,
            "memory_busy_timeout_ms": self.memory_busy_timeout_ms,
            "memory_recent_turn_limit": self.memory_recent_turn_limit,
            "memory_summary_after_turns": self.memory_summary_after_turns,
            "memory_summary_refresh_turns": self.memory_summary_refresh_turns,
            "memory_enable_auto_summary": self.memory_enable_auto_summary,
            "memory_enable_fact_extraction": self.memory_enable_fact_extraction,
            "memory_enable_sensitive_filter": self.memory_enable_sensitive_filter,
            "memory_enabled": self.memory_enabled,
            "memory_retention_days": self.memory_retention_days,
            "memory_cleanup_on_start": self.memory_cleanup_on_start,
            "memory_log_redaction": self.memory_log_redaction,
            "memory_trace_enabled": self.memory_trace_enabled,
        }
