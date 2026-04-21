# -*- coding: utf-8 -*-
"""
外部 Agent Runtime 启动器。

用于 product `agent.py` 中的外部 runtime 分发逻辑：
- claude_code
- trae
- codex
"""

from __future__ import annotations

import subprocess

from loguru import logger

SUPPORTED_RUNTIMES = ("claude_code", "trae", "codex")


def build_runtime_command(runtime: str, skill_prompt: str, codex_prompt: str) -> list[str]:
    """根据 runtime 名称构建外部命令。"""
    if runtime == "claude_code":
        return [
            "claude",
            "-p",
            skill_prompt,
            "--dangerously-skip-permissions",
            "--output-format",
            "json",
            "--no-session-persistence",
        ]

    if runtime == "trae":
        return ["trae", "-p", skill_prompt]

    if runtime == "codex":
        return [
            "codex",
            "--sandbox",
            "workspace-write",
            "--ask-for-approval",
            "never",
            "exec",
            "--color",
            "never",
            codex_prompt,
        ]

    raise ValueError(f"未知 AGENT_RUNTIME: {runtime}，支持: {list(SUPPORTED_RUNTIMES)}")


def run_skill_runtime(runtime: str, skill_prompt: str, codex_prompt: str) -> int:
    """执行外部 runtime，并返回退出码。"""
    try:
        cmd = build_runtime_command(runtime, skill_prompt=skill_prompt, codex_prompt=codex_prompt)
    except ValueError as exc:
        logger.error(str(exc))
        return 1

    logger.info(f"=== 使用 Runtime: {runtime} ===")
    return subprocess.run(cmd).returncode
