# -*- coding: utf-8 -*-
"""
Codex CLI Client — 通过 subprocess 调用 codex exec 的 AI 后端
"""

import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import List

from loguru import logger

from runtime.clients.base import AIClient


@dataclass
class CodexCLIConfig:
    """Codex CLI 客户端配置"""

    cli_path: str = "codex"
    model: str = ""
    profile: str = ""
    system_prompt: str = ""
    timeout: int = 300
    sandbox_mode: str = "read-only"
    approval_policy: str = "never"
    extra_args: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.cli_path = os.environ.get("CODEX_CLI_PATH", self.cli_path)
        self.model = os.environ.get("CODEX_MODEL", self.model)
        self.profile = os.environ.get("CODEX_PROFILE", self.profile)
        self.timeout = int(os.environ.get("CODEX_TIMEOUT", str(self.timeout)))
        self.sandbox_mode = os.environ.get("CODEX_SANDBOX", self.sandbox_mode)
        self.approval_policy = os.environ.get("CODEX_APPROVAL_POLICY", self.approval_policy)


class CodexCLIClient(AIClient):
    """
    通过 codex exec 子进程调用 Codex CLI 的后端。

    使用 `--output-last-message` 获取最终文本响应，并通过 stdin 传入 prompt，
    避免长 prompt 触发命令行长度限制。
    """

    def __init__(self, config: CodexCLIConfig):
        self.config = config
        self._check_cli_available()

    def _check_cli_available(self) -> bool:
        """检查 Codex CLI 是否可用"""
        try:
            result = subprocess.run(
                [self.config.cli_path, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                logger.info(f"Codex CLI 可用: {result.stdout.strip()}")
                return True
            logger.warning(f"Codex CLI 返回非零状态: {result.stderr}")
            return False
        except FileNotFoundError:
            logger.warning(f"Codex CLI 未找到: {self.config.cli_path}")
            return False
        except subprocess.TimeoutExpired:
            logger.warning("Codex CLI 版本检查超时")
            return False
        except Exception as e:
            logger.warning(f"检查 Codex CLI 时出错: {e}")
            return False

    def _build_command(self, last_message_path: str) -> List[str]:
        """构建 Codex CLI 命令"""
        cmd = [
            self.config.cli_path,
            "--sandbox",
            self.config.sandbox_mode,
            "--ask-for-approval",
            self.config.approval_policy,
        ]
        if self.config.model:
            cmd.extend(["--model", self.config.model])
        if self.config.profile:
            cmd.extend(["--profile", self.config.profile])
        cmd.extend(self.config.extra_args)
        cmd.extend(
            [
                "exec",
                "--skip-git-repo-check",
                "--color",
                "never",
                "--output-last-message",
                last_message_path,
                "-",
            ]
        )
        return cmd

    def _build_input(self, prompt: str) -> str:
        """构建传给 Codex 的最终 prompt。"""
        if self.config.system_prompt:
            return f"{self.config.system_prompt}\n\n{prompt}"
        return prompt

    def chat(self, prompt: str) -> str:
        """发送 prompt 到 Codex CLI 并返回最终文本响应"""
        fd, last_message_path = tempfile.mkstemp(prefix="codex-last-", suffix=".txt")
        os.close(fd)
        cmd = self._build_command(last_message_path)
        input_text = self._build_input(prompt)

        try:
            result = subprocess.run(
                cmd,
                input=input_text,
                capture_output=True,
                text=True,
                timeout=self.config.timeout + 30,
            )
            if result.returncode != 0:
                stderr = result.stderr.strip()
                stdout = result.stdout.strip()
                detail = stderr or stdout
                raise RuntimeError(f"Codex CLI 执行失败: {detail}")

            if not os.path.exists(last_message_path):
                raise RuntimeError("Codex CLI 未生成最终响应文件")

            with open(last_message_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
            if not content:
                raise RuntimeError("Codex CLI 返回空输出")

            return content

        except subprocess.TimeoutExpired:
            raise TimeoutError(f"Codex CLI 执行超时 ({self.config.timeout}s)")
        except Exception as e:
            logger.error(f"Codex CLI 执行出错: {e}")
            raise
        finally:
            try:
                os.remove(last_message_path)
            except OSError:
                pass
