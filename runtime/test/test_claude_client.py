# -*- coding: utf-8 -*-
"""
common.claude_client 单元测试
"""

import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from runtime.clients.claude import ClaudeClient, ClaudeClientConfig, MCPServerConfig

# ── MCPServerConfig ───────────────────────────────────────────────


class TestMCPServerConfig:
    def test_from_claude_json_all_types(self, tmp_path):
        cfg = {
            "mcpServers": {
                "doc-reader": {
                    "type": "stdio",
                    "command": "/usr/bin/python3",
                    "args": ["/path/to/doc_reader.py"],
                    "env": {},
                },
                "sentry": {
                    "type": "streamable-http",
                    "url": "https://mcp.sentry.dev/mcp",
                },
                "old-svc": {
                    "type": "sse",
                    "url": "https://example.com/sse",
                    "headers": {"X-Key": "abc"},
                },
            }
        }
        (tmp_path / ".claude.json").write_text(json.dumps(cfg))

        with patch.object(Path, "home", return_value=tmp_path):
            servers = MCPServerConfig.from_claude_json()

        assert len(servers) == 3
        by_name = {s.name: s for s in servers}

        assert by_name["doc-reader"].transport == "stdio"
        assert by_name["doc-reader"].command == "/usr/bin/python3"

        assert by_name["sentry"].transport == "http"
        assert by_name["sentry"].url == "https://mcp.sentry.dev/mcp"

        assert by_name["old-svc"].transport == "sse"
        assert by_name["old-svc"].headers == {"X-Key": "abc"}

    def test_from_claude_json_missing_file(self, tmp_path):
        with patch.object(Path, "home", return_value=tmp_path):
            servers = MCPServerConfig.from_claude_json()
        assert servers == []

    def test_stdio_requires_command(self):
        with pytest.raises(ValueError, match="command"):
            MCPServerConfig(name="x", transport="stdio")

    def test_http_requires_url(self):
        with pytest.raises(ValueError, match="url"):
            MCPServerConfig(name="x", transport="http")

    def test_invalid_transport(self):
        with pytest.raises(ValueError, match="transport"):
            MCPServerConfig(name="x", transport="ws", url="ws://x")


# ── ClaudeClientConfig ────────────────────────────────────────────


class TestClaudeClientConfig:
    def _settings(self, tmp_path, token="settings-token", base_url=""):
        d = tmp_path / ".claude"
        d.mkdir()
        data = {"env": {"ANTHROPIC_AUTH_TOKEN": token}}
        if base_url:
            data["env"]["ANTHROPIC_BASE_URL"] = base_url
        (d / "settings.json").write_text(json.dumps(data))
        return tmp_path

    def test_reads_token_from_env(self):
        with patch.dict(os.environ, {"ANTHROPIC_AUTH_TOKEN": "env-key"}):
            config = ClaudeClientConfig()
        assert config.auth_token == "env-key"

    def test_reads_token_from_settings_json(self, tmp_path):
        self._settings(tmp_path, token="file-token")
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)
            with patch.object(Path, "home", return_value=tmp_path):
                config = ClaudeClientConfig()
        assert config.auth_token == "file-token"

    def test_env_takes_precedence_over_settings(self, tmp_path):
        self._settings(tmp_path, token="file-token")
        with patch.dict(os.environ, {"ANTHROPIC_AUTH_TOKEN": "env-token"}):
            with patch.object(Path, "home", return_value=tmp_path):
                config = ClaudeClientConfig()
        assert config.auth_token == "env-token"

    def test_raises_without_token(self, tmp_path):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)
            with patch.object(Path, "home", return_value=tmp_path):
                with pytest.raises(ValueError, match="ANTHROPIC_AUTH_TOKEN"):
                    ClaudeClientConfig()

    def test_defaults(self):
        with patch.dict(os.environ, {"ANTHROPIC_AUTH_TOKEN": "k"}):
            config = ClaudeClientConfig()
        assert config.model == "claude-sonnet-4-6"
        assert config.max_tokens == 4096
        assert config.timeout == 300
        assert config.mcp_servers == []


# ── ClaudeClient (simple chat) ────────────────────────────────────


class TestClaudeClientSimpleChat:
    def _make_response(self, text: str, stop_reason: str = "end_turn"):
        block = MagicMock()
        block.text = text
        block.type = "text"
        resp = MagicMock()
        resp.content = [block]
        resp.stop_reason = stop_reason
        return resp

    def _client(self, mock_sdk_client, **cfg_kwargs):
        config = ClaudeClientConfig.__new__(ClaudeClientConfig)
        config.auth_token = "key"
        config.base_url = ""
        config.model = "claude-sonnet-4-6"
        config.system_prompt = cfg_kwargs.get("system_prompt", "")
        config.max_tokens = 4096
        config.timeout = 300
        config.mcp_servers = []

        client = ClaudeClient.__new__(ClaudeClient)
        client.config = config
        client._client = mock_sdk_client
        return client

    def test_basic(self):
        mock_sdk = MagicMock()
        mock_sdk.messages.create.return_value = self._make_response("hello")
        client = self._client(mock_sdk)

        result = client.chat("say hello")

        assert result == "hello"
        call_kwargs = mock_sdk.messages.create.call_args[1]
        assert call_kwargs["messages"] == [{"role": "user", "content": "say hello"}]
        assert "system" not in call_kwargs

    def test_with_system_prompt(self):
        mock_sdk = MagicMock()
        mock_sdk.messages.create.return_value = self._make_response("ok")
        client = self._client(mock_sdk, system_prompt="你是助手")

        client.chat("问题")

        call_kwargs = mock_sdk.messages.create.call_args[1]
        assert call_kwargs["system"] == "你是助手"

    def test_raises_on_api_error(self):
        mock_sdk = MagicMock()
        mock_sdk.messages.create.side_effect = RuntimeError("API error")
        client = self._client(mock_sdk)

        with pytest.raises(RuntimeError, match="API error"):
            client.chat("prompt")


# ── ClaudeClient (MCP tool-use loop) ─────────────────────────────


class TestClaudeClientMCP:
    """测试 MCP tool-use 循环，mock 掉 MCP 子进程和 Anthropic SDK。"""

    def _make_tool_use_response(self, tool_id: str, tool_name: str, tool_input: dict):
        block = MagicMock()
        block.type = "tool_use"
        block.id = tool_id
        block.name = tool_name
        block.input = tool_input
        resp = MagicMock()
        resp.content = [block]
        resp.stop_reason = "tool_use"
        return resp

    def _make_text_response(self, text: str):
        block = MagicMock()
        block.type = "text"
        block.text = text
        resp = MagicMock()
        resp.content = [block]
        resp.stop_reason = "end_turn"
        return resp

    def _make_mcp_tool(self, name: str, description: str):
        tool = MagicMock()
        tool.name = name
        tool.description = description
        tool.inputSchema = {"type": "object", "properties": {}}
        return tool

    def _make_mcp_text_content(self, text: str):
        item = MagicMock()
        item.text = text
        return item

    def test_tool_use_loop(self):
        """验证：模型调用一次工具后继续对话并返回最终文本。"""
        srv_cfg = MCPServerConfig(
            name="doc-reader",
            command="/usr/bin/python3",
            args=["/path/to/server.py"],
        )

        config = ClaudeClientConfig.__new__(ClaudeClientConfig)
        config.auth_token = "key"
        config.base_url = ""
        config.model = "claude-sonnet-4-6"
        config.system_prompt = ""
        config.max_tokens = 4096
        config.timeout = 300
        config.mcp_servers = [srv_cfg]

        mock_sdk = MagicMock()
        mock_sdk.messages.create.side_effect = [
            self._make_tool_use_response("id1", "doc-reader__read_document", {"path": "a.pdf"}),
            self._make_text_response("文档内容是 XYZ"),
        ]

        # Mock MCP session
        mock_session = AsyncMock()
        mock_session.list_tools.return_value = MagicMock(tools=[self._make_mcp_tool("read_document", "读取文档")])
        mock_session.call_tool.return_value = MagicMock(content=[self._make_mcp_text_content("XYZ 内容")])

        client = ClaudeClient.__new__(ClaudeClient)
        client.config = config
        client._client = mock_sdk

        async def run():
            async with AsyncExitStack() as _:
                pass  # just to import

        # Patch stdio_client and ClientSession
        with patch("runtime.clients.claude.stdio_client") as mock_stdio, patch(
            "runtime.clients.claude.ClientSession"
        ) as mock_session_cls:

            mock_stdio.return_value.__aenter__ = AsyncMock(return_value=(AsyncMock(), AsyncMock()))
            mock_stdio.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = client.chat("读取 a.pdf")

        assert result == "文档内容是 XYZ"
        assert mock_sdk.messages.create.call_count == 2
        mock_session.call_tool.assert_called_once_with("read_document", {"path": "a.pdf"})


# 导入 AsyncExitStack 供测试使用
from contextlib import AsyncExitStack  # noqa: E402
