# -*- coding: utf-8 -*-
"""
Claude Client — 基于 Anthropic Python SDK 的 AI 后端（默认后端）
读取 ~/.claude/settings.json 中的 env 字段作为配置入口。
支持 MCP tool-use 循环（stdio / http / sse 三种传输）。
"""

import asyncio
import concurrent.futures
import json
import os
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from pathlib import Path

from loguru import logger

from runtime.clients.base import AIClient

try:
    from mcp import ClientSession
    from mcp.client.sse import sse_client
    from mcp.client.stdio import StdioServerParameters, stdio_client
    from mcp.client.streamable_http import streamablehttp_client

    _MCP_AVAILABLE = True
except ImportError:
    _MCP_AVAILABLE = False


# ── MCP 服务器配置 ────────────────────────────────────────────────


@dataclass
class MCPServerConfig:
    """
    单个 MCP 服务器的配置，支持 stdio / http / sse 三种传输。

    stdio 示例（本地脚本）：
        MCPServerConfig(name="doc-reader", transport="stdio",
                        command="python3", args=["/path/doc_reader.py"])

    http 示例（远程云服务）：
        MCPServerConfig(name="sentry", transport="http",
                        url="https://mcp.sentry.dev/mcp",
                        headers={"Authorization": "Bearer TOKEN"})
    """

    name: str
    transport: str = "stdio"  # "stdio" | "http" | "sse"

    # stdio 专用
    command: str = ""
    args: list = field(default_factory=list)
    env: dict = field(default_factory=dict)

    # http / sse 专用
    url: str = ""
    headers: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.transport not in ("stdio", "http", "sse"):
            raise ValueError(f"transport 必须是 stdio/http/sse，收到: {self.transport}")
        if self.transport == "stdio" and not self.command:
            raise ValueError(f"stdio 传输必须提供 command（服务器: {self.name}）")
        if self.transport in ("http", "sse") and not self.url:
            raise ValueError(f"{self.transport} 传输必须提供 url（服务器: {self.name}）")

    @classmethod
    def from_claude_json(cls) -> list["MCPServerConfig"]:
        """
        从 ~/.claude.json 读取用户级 MCP 服务器配置。
        支持 stdio / http / sse 三种类型。
        """
        path = Path.home() / ".claude.json"
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return []

        servers = []
        for name, cfg in data.get("mcpServers", {}).items():
            t = cfg.get("type", "stdio")
            try:
                if t == "stdio" and cfg.get("command"):
                    servers.append(
                        cls(
                            name=name,
                            transport="stdio",
                            command=cfg["command"],
                            args=cfg.get("args", []),
                            env=cfg.get("env") or {},
                        )
                    )
                elif t in ("streamable-http", "http") and cfg.get("url"):
                    servers.append(
                        cls(
                            name=name,
                            transport="http",
                            url=cfg["url"],
                            headers=cfg.get("headers") or {},
                        )
                    )
                elif t == "sse" and cfg.get("url"):
                    servers.append(
                        cls(
                            name=name,
                            transport="sse",
                            url=cfg["url"],
                            headers=cfg.get("headers") or {},
                        )
                    )
            except ValueError as e:
                logger.warning(f"跳过无效 MCP 服务器配置 [{name}]: {e}")
        return servers


# ── ClaudeClient 配置 ─────────────────────────────────────────────


@dataclass
class ClaudeClientConfig:
    """Claude 客户端配置"""

    auth_token: str = ""
    base_url: str = ""
    model: str = "claude-sonnet-4-6"
    system_prompt: str = ""
    max_tokens: int = 4096
    timeout: int = 300
    # MCP 服务器列表；为空时退化为普通 chat，不建立任何连接
    mcp_servers: list = field(default_factory=list)

    def __post_init__(self):
        settings = self._load_settings()

        if not self.auth_token:
            self.auth_token = os.environ.get("ANTHROPIC_AUTH_TOKEN", "") or settings.get("env", {}).get(
                "ANTHROPIC_AUTH_TOKEN", ""
            )
        if not self.base_url:
            self.base_url = os.environ.get("ANTHROPIC_BASE_URL", "") or settings.get("env", {}).get(
                "ANTHROPIC_BASE_URL", ""
            )
        if not self.auth_token:
            raise ValueError("ANTHROPIC_AUTH_TOKEN 未设置（环境变量或 ~/.claude/settings.json 均未找到）")

    @staticmethod
    def _load_settings() -> dict:
        path = Path.home() / ".claude" / "settings.json"
        if path.exists():
            try:
                return json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                pass
        return {}


# ── ClaudeClient ──────────────────────────────────────────────────


class ClaudeClient(AIClient):
    """
    基于 Anthropic SDK 的 Claude 客户端，接口与 TraeCLIClient 兼容。

    当 config.mcp_servers 不为空时，自动连接 MCP 服务器并执行完整的
    tool-use 循环；否则退化为简单的单轮对话。

    快速启用本地 MCP（读取 ~/.claude.json 中已注册的服务器）：
        cfg = ClaudeClientConfig(mcp_servers=MCPServerConfig.from_claude_json())
        client = ClaudeClient(cfg)

    混合使用本地 + 远程 MCP：
        cfg = ClaudeClientConfig(mcp_servers=[
            MCPServerConfig(name="doc-reader", transport="stdio",
                            command="python3", args=["/path/doc_reader.py"]),
            MCPServerConfig(name="sentry", transport="http",
                            url="https://mcp.sentry.dev/mcp",
                            headers={"Authorization": "Bearer TOKEN"}),
        ])
    """

    def __init__(self, config: ClaudeClientConfig):
        self.config = config
        try:
            import anthropic

            kwargs = {
                "api_key": self.config.auth_token,
                "timeout": float(self.config.timeout),
            }
            if self.config.base_url:
                kwargs["base_url"] = self.config.base_url
            self._client = anthropic.Anthropic(**kwargs)  # type: ignore[arg-type]
            logger.info(
                f"Claude 客户端初始化完成: model={self.config.model}, "
                f"mcp_servers={[s.name for s in self.config.mcp_servers]}"
            )
        except ImportError:
            raise RuntimeError("anthropic 未安装，请运行: pip install anthropic>=0.40.0")

    # ── 公共接口（同步） ─────────────────────────────────────────

    def chat(self, prompt: str) -> str:
        """
        发送 prompt 并获取响应，接口与 TraeCLIClient.chat() 完全兼容。
        若配置了 mcp_servers，内部执行完整的 tool-use 循环。
        """
        if not self.config.mcp_servers:
            return self._simple_chat(prompt)

        # 在独立线程中运行异步逻辑，避免与调用方事件循环冲突
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, self._chat_with_mcp(prompt))
            return future.result()

    # ── 简单对话（无 MCP） ───────────────────────────────────────

    def _simple_chat(self, prompt: str) -> str:
        kwargs = {
            "model": self.config.model,
            "max_tokens": self.config.max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if self.config.system_prompt:
            kwargs["system"] = self.config.system_prompt
        try:
            response = self._client.messages.create(**kwargs)  # type: ignore[call-overload]
            return response.content[0].text
        except Exception as e:
            logger.error(f"Claude API 调用失败: {e}")
            raise

    # ── MCP 连接（按传输类型） ────────────────────────────────────

    async def _connect_server(self, srv: MCPServerConfig, stack: AsyncExitStack):
        """建立连接并返回 (read, write)，屏蔽三种传输的差异。"""
        if srv.transport == "stdio":
            params = StdioServerParameters(
                command=srv.command,
                args=srv.args,
                env={**os.environ, **srv.env} if srv.env else None,
            )
            return await stack.enter_async_context(stdio_client(params))

        if srv.transport == "http":
            conn = await stack.enter_async_context(streamablehttp_client(srv.url, headers=srv.headers or None))
            read, write, _get_session_id = conn  # HTTP 返回三元组
            return read, write

        if srv.transport == "sse":
            return await stack.enter_async_context(sse_client(srv.url, headers=srv.headers or None))

        raise ValueError(f"不支持的传输类型: {srv.transport}")

    # ── MCP tool-use 循环（异步） ────────────────────────────────

    async def _chat_with_mcp(self, prompt: str) -> str:
        """
        连接所有 MCP 服务器 → 收集工具列表 → 执行 tool-use 循环 → 返回最终文本。
        所有连接在整个对话期间保持，对话结束后统一关闭。
        """
        if not _MCP_AVAILABLE:
            raise RuntimeError("mcp 未安装，请运行: pip install mcp")

        # server_name -> session
        server_sessions: dict[str, object] = {}
        anthropic_tools: list[dict] = []

        async with AsyncExitStack() as stack:
            # ── 建立连接并收集工具 ───────────────────────────────
            for srv in self.config.mcp_servers:
                try:
                    read, write = await self._connect_server(srv, stack)
                    session = await stack.enter_async_context(ClientSession(read, write))
                    await session.initialize()

                    tools_result = await session.list_tools()
                    for tool in tools_result.tools:
                        # {server_name}__{tool_name} 防止不同服务器的同名工具冲突
                        qualified = f"{srv.name}__{tool.name}"
                        anthropic_tools.append(
                            {
                                "name": qualified,
                                "description": tool.description or "",
                                "input_schema": tool.inputSchema or {"type": "object", "properties": {}},
                            }
                        )
                    server_sessions[srv.name] = session
                    logger.debug(
                        f"MCP [{srv.name}/{srv.transport}] 已连接，" f"工具: {[t.name for t in tools_result.tools]}"
                    )
                except Exception as e:
                    logger.warning(f"MCP [{srv.name}] 连接失败，跳过: {e}")

            if not anthropic_tools:
                logger.warning("所有 MCP 服务器均无可用工具，退化为普通对话")
                return self._simple_chat(prompt)

            # ── tool-use 循环 ────────────────────────────────────
            messages = [{"role": "user", "content": prompt}]

            while True:
                kwargs: dict = {
                    "model": self.config.model,
                    "max_tokens": self.config.max_tokens,
                    "messages": messages,
                    "tools": anthropic_tools,
                }
                if self.config.system_prompt:
                    kwargs["system"] = self.config.system_prompt

                response = self._client.messages.create(**kwargs)
                logger.debug(f"API 响应 stop_reason={response.stop_reason}")

                if response.stop_reason in ("end_turn", None):
                    return self._extract_text(response.content)

                if response.stop_reason != "tool_use":
                    return self._extract_text(response.content)

                # ── 执行工具调用 ─────────────────────────────────
                tool_results = []
                for block in response.content:
                    if block.type != "tool_use":
                        continue

                    server_name, tool_name = block.name.split("__", 1)
                    if server_name not in server_sessions:
                        tool_results.append(self._tool_error(block.id, f"未知服务器: {server_name}"))
                        continue

                    try:
                        logger.debug(f"调用 [{server_name}] {tool_name}({block.input})")
                        result = await server_sessions[server_name].call_tool(tool_name, block.input)  # type: ignore[attr-defined]  # noqa: E501
                        content = [
                            {"type": "text", "text": item.text} for item in result.content if hasattr(item, "text")
                        ]
                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": content or [{"type": "text", "text": "(空响应)"}],
                            }
                        )
                    except Exception as e:
                        logger.error(f"工具 [{server_name}] {tool_name} 失败: {e}")
                        tool_results.append(self._tool_error(block.id, str(e)))

                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": tool_results})  # type: ignore[dict-item]

    # ── 工具函数 ─────────────────────────────────────────────────

    @staticmethod
    def _extract_text(content: list) -> str:
        for block in content:
            if hasattr(block, "text"):
                return block.text
        return ""

    @staticmethod
    def _tool_error(tool_use_id: str, message: str) -> dict:
        return {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": [{"type": "text", "text": f"工具调用失败: {message}"}],
            "is_error": True,
        }
