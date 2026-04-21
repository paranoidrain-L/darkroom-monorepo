# -*- coding: utf-8 -*-
"""
Claude Code CLI Client — 通过 claude -p 子进程调用的 AI 后端

与 SDK 后端（claude.py）的区别：
  - 不直接调用 Anthropic API，而是委托给本地 claude CLI
  - API Key 使用 Claude Code 订阅 Key（不受 allowedClients 限制）
  - 无需额外安装 anthropic 包
"""

import json
import subprocess
from dataclasses import dataclass, field
from typing import List

from loguru import logger

from runtime.clients.base import AIClient


@dataclass
class ClaudeCodeCLIConfig:
    """Claude Code CLI 客户端配置"""

    cli_path: str = "claude"
    model: str = ""  # 空字符串使用 Claude Code 默认模型
    system_prompt: str = ""
    timeout: int = 300
    allowed_tools: str = ""  # 默认禁用所有工具，只做纯文本对话
    extra_args: List[str] = field(default_factory=list)


class ClaudeCodeCLIClient(AIClient):
    """
    通过 claude -p 子进程调用 Claude Code CLI 的后端。

    等价命令示例：
        claude -p --output-format json --tools "" --no-session-persistence \\
               --model claude-sonnet-4-6 --system-prompt "..." "your prompt"
    """

    def __init__(self, config: ClaudeCodeCLIConfig):
        self.config = config
        self._check_cli_available()

    def _check_cli_available(self) -> bool:
        """检查 claude CLI 是否可用"""
        try:
            result = subprocess.run(
                [self.config.cli_path, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                logger.info(f"Claude Code CLI 可用: {result.stdout.strip()}")
                return True
            logger.warning(f"Claude Code CLI 返回非零状态: {result.stderr}")
            return False
        except FileNotFoundError:
            logger.warning(f"Claude Code CLI 未找到: {self.config.cli_path}")
            return False
        except subprocess.TimeoutExpired:
            logger.warning("Claude Code CLI 版本检查超时")
            return False
        except Exception as e:
            logger.warning(f"检查 Claude Code CLI 时出错: {e}")
            return False

    def _build_command(self, prompt: str) -> List[str]:
        """构建 claude CLI 命令"""
        cmd = [
            self.config.cli_path,
            "-p",
            prompt,
            "--output-format",
            "json",
            "--no-session-persistence",
            "--tools",
            self.config.allowed_tools,
        ]
        if self.config.model:
            cmd.extend(["--model", self.config.model])
        if self.config.system_prompt:
            cmd.extend(["--append-system-prompt", self.config.system_prompt])
        cmd.extend(self.config.extra_args)
        return cmd

    def chat(self, prompt: str) -> str:
        """发送 prompt 到 Claude Code CLI 并返回纯文本响应"""
        cmd = self._build_command(prompt)
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.config.timeout + 30,
            )
            if result.returncode != 0:
                raise RuntimeError(f"Claude Code CLI 执行失败: {result.stderr.strip()}")

            output = result.stdout.strip()
            if not output:
                raise RuntimeError("Claude Code CLI 返回空输出")

            data = json.loads(output)

            if data.get("is_error"):
                raise RuntimeError(f"Claude Code CLI 返回错误: {data.get('result', output)}")

            content = data.get("result", "")
            if not content:
                raise RuntimeError(f"Claude Code CLI 响应中 result 字段为空: {output[:500]}")

            return content

        except json.JSONDecodeError:
            raise RuntimeError(f"Claude Code CLI 输出不是合法 JSON: {result.stdout[:500]}")
        except subprocess.TimeoutExpired:
            raise TimeoutError(f"Claude Code CLI 执行超时 ({self.config.timeout}s)")
        except Exception as e:
            logger.error(f"Claude Code CLI 执行出错: {e}")
            raise
