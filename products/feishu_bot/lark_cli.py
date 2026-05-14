# -*- coding: utf-8 -*-
"""Thin wrapper around the official `lark-cli` binary."""

from __future__ import annotations

import json
import os
import subprocess
from typing import Any


class LarkCLIError(RuntimeError):
    """Raised when lark-cli fails."""


class LarkCLI:
    """Execute Lark operations through `lark-cli`."""

    def __init__(self, cli_path: str = "lark-cli", timeout: int = 30) -> None:
        self.cli_path = cli_path
        self.timeout = timeout

    def ensure_available(self) -> None:
        try:
            result = subprocess.run(
                [self.cli_path, "--version"],
                capture_output=True,
                text=True,
                timeout=min(self.timeout, 10),
            )
        except FileNotFoundError as exc:
            raise LarkCLIError(
                f"未找到 lark-cli: {self.cli_path}。请先执行 `npm install -g @larksuite/cli`。"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise LarkCLIError("检查 lark-cli 可用性超时。") from exc

        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            raise LarkCLIError(f"lark-cli 不可用: {detail}")

    def show_config(self) -> dict[str, Any]:
        return self._run_json(["config", "show"])

    def reply_text(self, message_id: str, content: str) -> dict[str, Any]:
        return self._run_json(
            [
                "im",
                "+messages-reply",
                "--as",
                "bot",
                "--message-id",
                message_id,
                "--text",
                content,
            ]
        )

    def send_text_to_chat(self, chat_id: str, content: str) -> dict[str, Any]:
        return self._run_json(
            [
                "im",
                "+messages-send",
                "--as",
                "bot",
                "--chat-id",
                chat_id,
                "--text",
                content,
            ]
        )

    def subscribe_events(self, *, event_types: str | None = None) -> subprocess.Popen[str]:
        command = [self.cli_path, "event", "+subscribe", "--as", "bot", "--quiet"]
        if event_types:
            command.extend(["--event-types", event_types])
        try:
            return subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
        except FileNotFoundError as exc:
            raise LarkCLIError(
                f"未找到 lark-cli: {self.cli_path}。请先执行 `npm install -g @larksuite/cli`。"
            ) from exc

    def download_message_resource(
        self,
        *,
        message_id: str,
        file_key: str,
        output_path: str,
        resource_type: str = "file",
    ) -> str:
        if os.path.isabs(output_path) or ".." in output_path.split(os.sep):
            raise LarkCLIError("lark-cli 下载路径必须是安全的相对路径。")

        self._run_json(
            [
                "im",
                "+messages-resources-download",
                "--as",
                "bot",
                "--message-id",
                message_id,
                "--file-key",
                file_key,
                "--type",
                resource_type,
                "--output",
                output_path,
            ]
        )
        return output_path

    def _run_json(self, args: list[str]) -> dict[str, Any]:
        command = [self.cli_path, *args]
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
        except FileNotFoundError as exc:
            raise LarkCLIError(
                f"未找到 lark-cli: {self.cli_path}。请先执行 `npm install -g @larksuite/cli`。"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise LarkCLIError(f"lark-cli 执行超时: {' '.join(command)}") from exc

        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            raise LarkCLIError(detail or f"lark-cli 执行失败: {' '.join(command)}")

        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise LarkCLIError(f"lark-cli 输出不是合法 JSON: {result.stdout[:500]}") from exc
