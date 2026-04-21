# -*- coding: utf-8 -*-
"""
runtime.clients.codex 单元测试
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from runtime.clients.codex import CodexCLIClient, CodexCLIConfig


class TestCodexCLIConfig:
    def test_default_values(self):
        config = CodexCLIConfig()
        assert config.cli_path == "codex"
        assert config.model == ""
        assert config.profile == ""
        assert config.timeout == 300
        assert config.sandbox_mode == "read-only"
        assert config.approval_policy == "never"

    def test_custom_values(self):
        config = CodexCLIConfig(
            cli_path="/custom/codex",
            model="gpt-5.4",
            profile="ci",
            timeout=60,
            sandbox_mode="workspace-write",
            approval_policy="on-request",
        )
        assert config.cli_path == "/custom/codex"
        assert config.model == "gpt-5.4"
        assert config.profile == "ci"
        assert config.timeout == 60
        assert config.sandbox_mode == "workspace-write"
        assert config.approval_policy == "on-request"


class TestCodexCLIClient:
    def setup_method(self):
        self.config = CodexCLIConfig(cli_path="codex", timeout=10)

    @patch("runtime.clients.codex.subprocess.run")
    def test_check_cli_available_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="codex 1.0.0", stderr="")
        client = CodexCLIClient(self.config)
        assert client._check_cli_available() is True

    @patch("runtime.clients.codex.subprocess.run")
    def test_check_cli_not_found(self, mock_run):
        mock_run.side_effect = FileNotFoundError()
        client = CodexCLIClient.__new__(CodexCLIClient)
        client.config = self.config
        assert client._check_cli_available() is False

    def test_build_command_basic(self):
        client = CodexCLIClient.__new__(CodexCLIClient)
        client.config = CodexCLIConfig(cli_path="codex")
        cmd = client._build_command("/tmp/last.txt")
        assert cmd[:3] == ["codex", "--sandbox", "read-only"]
        assert "--ask-for-approval" in cmd
        assert "exec" in cmd
        assert "--output-last-message" in cmd
        assert cmd[-1] == "-"

    def test_build_command_with_model_and_profile(self):
        client = CodexCLIClient.__new__(CodexCLIClient)
        client.config = CodexCLIConfig(
            cli_path="codex",
            model="gpt-5.4",
            profile="ci",
            sandbox_mode="workspace-write",
        )
        cmd = client._build_command("/tmp/last.txt")
        assert "--model" in cmd
        assert "gpt-5.4" in cmd
        assert "--profile" in cmd
        assert "ci" in cmd
        assert "workspace-write" in cmd

    def test_build_input_with_system_prompt(self):
        client = CodexCLIClient.__new__(CodexCLIClient)
        client.config = CodexCLIConfig(system_prompt="你是代码审查专家。")
        text = client._build_input("请审查以下变更")
        assert text == "你是代码审查专家。\n\n请审查以下变更"

    @patch("runtime.clients.codex.subprocess.run")
    def test_chat_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        client = CodexCLIClient.__new__(CodexCLIClient)
        client.config = CodexCLIConfig(cli_path="codex", timeout=10)

        with tempfile.NamedTemporaryFile("w+", delete=False, encoding="utf-8") as f:
            f.write("final answer")
            temp_path = f.name

        with patch("runtime.clients.codex.tempfile.mkstemp", return_value=(123, temp_path)), patch(
            "runtime.clients.codex.os.close"
        ), patch("runtime.clients.codex.os.remove"):
            result = client.chat("hello")

        assert result == "final answer"
        call_kwargs = mock_run.call_args.kwargs
        assert call_kwargs["input"] == "hello"

    @patch("runtime.clients.codex.subprocess.run")
    def test_chat_raises_on_nonzero_exit(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="boom")
        client = CodexCLIClient.__new__(CodexCLIClient)
        client.config = CodexCLIConfig(cli_path="codex", timeout=10)

        with tempfile.NamedTemporaryFile("w+", delete=False, encoding="utf-8") as f:
            temp_path = f.name

        with patch("runtime.clients.codex.tempfile.mkstemp", return_value=(123, temp_path)), patch(
            "runtime.clients.codex.os.close"
        ), patch("runtime.clients.codex.os.remove"):
            with pytest.raises(RuntimeError, match="boom"):
                client.chat("hello")

    @patch("runtime.clients.codex.subprocess.run")
    def test_chat_raises_on_empty_output(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        client = CodexCLIClient.__new__(CodexCLIClient)
        client.config = CodexCLIConfig(cli_path="codex", timeout=10)

        with tempfile.NamedTemporaryFile("w+", delete=False, encoding="utf-8") as f:
            temp_path = f.name

        Path(temp_path).write_text("", encoding="utf-8")

        with patch("runtime.clients.codex.tempfile.mkstemp", return_value=(123, temp_path)), patch(
            "runtime.clients.codex.os.close"
        ), patch("runtime.clients.codex.os.remove"):
            with pytest.raises(RuntimeError, match="空输出"):
                client.chat("hello")
