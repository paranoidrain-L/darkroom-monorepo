# -*- coding: utf-8 -*-
"""File-message helpers for Feishu bot."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Callable

from loguru import logger

from products.feishu_bot.handlers.context import FileInfo, SessionContextManager
from products.feishu_bot.lark_cli import LarkCLI
from runtime.memory import MemoryScope

SUPPORTED_FILE_KINDS = {
    ".txt",
    ".md",
    ".json",
    ".xml",
    ".yaml",
    ".yml",
    ".csv",
    ".log",
    ".ini",
    ".conf",
    ".cfg",
    ".py",
    ".js",
    ".ts",
    ".java",
    ".c",
    ".cpp",
    ".h",
    ".go",
    ".rs",
    ".rb",
    ".php",
    ".swift",
    ".kt",
    ".sh",
    ".bat",
    ".ps1",
    ".toml",
    ".env",
    ".dockerfile",
    ".makefile",
}

SPECIAL_FILE_KINDS = {
    ".env": ".env",
    "dockerfile": ".dockerfile",
    "makefile": ".makefile",
}


def extract_file_info(content: str) -> dict[str, Any]:
    try:
        content_dict = json.loads(content) if isinstance(content, str) else content
    except json.JSONDecodeError:
        return {"file_key": "", "file_name": "", "file_size": 0}
    return {
        "file_key": content_dict.get("file_key", ""),
        "file_name": content_dict.get("file_name", ""),
        "file_size": content_dict.get("file_size", 0),
    }


def resolve_file_kind(file_name: str) -> str:
    lower_name = os.path.basename(file_name).lower()
    if lower_name in SPECIAL_FILE_KINDS:
        return SPECIAL_FILE_KINDS[lower_name]
    return os.path.splitext(lower_name)[1]


def safe_file_name(file_name: str) -> str:
    base_name = os.path.basename(file_name).strip()
    if not base_name:
        return "file"
    return re.sub(r"[^A-Za-z0-9._-]", "_", base_name)


def relative_download_path(download_dir: str, message_id: str, file_name: str) -> str:
    safe_name = safe_file_name(file_name)
    base_dir = download_dir.strip("./") or "downloads"
    relative_path = os.path.join(base_dir, f"{message_id}_{safe_name}")
    os.makedirs(os.path.dirname(relative_path), exist_ok=True)
    return relative_path


def read_file_content(file_path: str, max_size: int = 100000) -> str:
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read(max_size)
    except UnicodeDecodeError:
        try:
            with open(file_path, "r", encoding="gbk") as f:
                content = f.read(max_size)
        except Exception:
            return "[无法读取文件内容：编码不支持]"
    except Exception as exc:
        return f"[读取文件失败：{exc}]"

    if len(content) == max_size:
        return content + "\n... (文件内容过长，已截断)"
    return content


def build_file_prompt(file_info: FileInfo, user_message: str) -> str:
    return (
        f"用户上传了一个文件：{file_info.file_name}\n"
        f"文件类型：{file_info.file_kind or 'unknown'}\n\n"
        f"文件内容：\n```\n{file_info.file_content}\n```\n\n"
        f"用户说：{user_message}"
    )


class FeishuFileFlow:
    """Handles Feishu file download and pending-file state."""

    def __init__(
        self,
        *,
        download_dir: str,
        lark_cli: LarkCLI,
        context_manager: SessionContextManager,
        context_key: Callable[[MemoryScope], str],
        reply_text: Callable[[str, str], bool],
        log_conversation: Callable[..., str],
        trace_builder: Callable[..., dict[str, Any]],
        trace_enabled: bool,
        log_redaction: bool,
    ) -> None:
        self.download_dir = download_dir
        self.lark_cli = lark_cli
        self.context_manager = context_manager
        self.context_key = context_key
        self.reply_text = reply_text
        self.log_conversation = log_conversation
        self.trace_builder = trace_builder
        self.trace_enabled = trace_enabled
        self.log_redaction = log_redaction

    def handle_file_message(
        self,
        *,
        message_id: str,
        sender_id: str,
        content: str,
        scope: MemoryScope,
    ) -> None:
        payload = extract_file_info(content)
        file_key = payload["file_key"]
        file_name = payload["file_name"] or "unknown"

        if not file_key:
            self.reply_text(message_id, "文件消息缺少 file_key，无法下载。")
            return

        file_kind = resolve_file_kind(file_name)
        if file_kind not in SUPPORTED_FILE_KINDS:
            self.reply_text(
                message_id,
                f"暂不支持该文件格式：{file_name}\n支持的格式：{', '.join(sorted(SUPPORTED_FILE_KINDS))}",
            )
            return

        try:
            relative_output = relative_download_path(self.download_dir, message_id, file_name)
            file_path = self.lark_cli.download_message_resource(
                message_id=message_id,
                file_key=file_key,
                output_path=relative_output,
                resource_type="file",
            )
            file_content = read_file_content(file_path)
        except Exception as exc:
            logger.error(f"下载或读取文件失败: {exc}")
            self.reply_text(message_id, f"下载文件失败：{exc}")
            return

        self.context_manager.set_pending_file(
            self.context_key(scope),
            FileInfo(
                file_path=file_path,
                file_name=file_name,
                file_kind=file_kind,
                file_content=file_content,
            ),
        )

        self.reply_text(message_id, f"已收到文件：{file_name}\n请告诉我您想对这个文件做什么？")
        self.log_conversation(
            user_id=sender_id,
            user_message=f"[上传文件] {file_name}",
            ai_response="已收到文件，等待用户指示",
            message_id=message_id,
            trace=self.trace_builder(scope=scope, event="file_pending") if self.trace_enabled else None,
            redact=self.log_redaction,
        )
