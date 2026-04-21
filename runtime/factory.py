# -*- coding: utf-8 -*-
"""
AI 后端工厂 — 统一后端选择入口

默认后端：claude（读取 ~/.claude/settings.json 或环境变量）
可选后端：trae / claude_code / codex（调用本地 CLI subprocess）

用法：
    from runtime.factory import get_client
    client = get_client()                   # 默认 claude
    client = get_client(backend="trae")     # 指定 trae
    client = get_client(backend="codex")    # 指定 codex
    result = client.chat("你好")
"""

from __future__ import annotations

from runtime.clients.base import AIClient


def get_client(backend: str = "claude", **kwargs) -> AIClient:
    """
    创建并返回 AI 客户端。

    Args:
        backend: 后端名称，支持 claude / claude_code / trae / codex
        **kwargs: 透传给对应 Config 的额外参数（如 model, system_prompt 等）

    Returns:
        AIClient 实例
    """
    if backend == "claude":
        from runtime.clients.claude import ClaudeClient, ClaudeClientConfig

        return ClaudeClient(ClaudeClientConfig(**kwargs))

    if backend == "trae":
        from dataclasses import fields

        from runtime.clients.trae import TraeCLIClient, TraeClientConfig

        valid_keys = {f.name for f in fields(TraeClientConfig)}
        trae_kwargs = {k: v for k, v in kwargs.items() if k in valid_keys}
        return TraeCLIClient(TraeClientConfig(**trae_kwargs))

    if backend == "claude_code":
        from dataclasses import fields

        from runtime.clients.claude_code import ClaudeCodeCLIClient, ClaudeCodeCLIConfig

        valid_keys = {f.name for f in fields(ClaudeCodeCLIConfig)}
        cc_kwargs = {k: v for k, v in kwargs.items() if k in valid_keys}
        return ClaudeCodeCLIClient(ClaudeCodeCLIConfig(**cc_kwargs))

    if backend == "codex":
        from dataclasses import fields

        from runtime.clients.codex import CodexCLIClient, CodexCLIConfig

        valid_keys = {f.name for f in fields(CodexCLIConfig)}
        codex_kwargs = {k: v for k, v in kwargs.items() if k in valid_keys}
        return CodexCLIClient(CodexCLIConfig(**codex_kwargs))

    raise ValueError(f"未知后端: {backend!r}，支持的后端: claude, claude_code, trae, codex")
