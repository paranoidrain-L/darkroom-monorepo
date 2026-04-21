# -*- coding: utf-8 -*-
"""
common.trae_client 单元测试
"""

from unittest.mock import MagicMock, patch

import pytest

from runtime.clients.trae import (
    TraeCLIClient,
    TraeClientConfig,
    _extract_issues_array,
    _repair_json_builtin,
    repair_json,
)


class TestTraeClientConfig:
    def test_default_values(self):
        config = TraeClientConfig()
        assert config.trae_cli_path == "trae-cli"
        assert config.model == ""
        assert config.agent == ""
        assert config.timeout == 300
        assert config.yolo is True

    def test_custom_values(self):
        config = TraeClientConfig(
            trae_cli_path="/custom/trae",
            model="gpt-4",
            timeout=60,
            yolo=False,
        )
        assert config.trae_cli_path == "/custom/trae"
        assert config.model == "gpt-4"
        assert config.timeout == 60
        assert config.yolo is False


class TestRepairJson:
    def test_valid_json(self):
        data = repair_json('{"key": "value"}')
        assert data == {"key": "value"}

    def test_invalid_json_with_builtin(self):
        # 有效 JSON 对象但带有额外内容
        data = repair_json('{"issues": [], "summary": "ok"}')
        assert "issues" in data

    def test_empty_raises(self):
        with pytest.raises(Exception):
            _repair_json_builtin("not json at all")


class TestRepairJsonBuiltin:
    def test_extract_valid_json(self):
        data = _repair_json_builtin('prefix {"key": "value"} suffix')
        assert data == {"key": "value"}

    def test_string_concatenation_fix(self):
        # 修复 "a" + "b" 形式
        data = _repair_json_builtin('{"key": "hel" + "lo"}')
        assert data == {"key": "hello"}

    def test_no_json_raises(self):
        with pytest.raises(RuntimeError):
            _repair_json_builtin("no braces here")


class TestExtractIssuesArray:
    def test_extract_valid_issues(self):
        json_str = '{"issues": [{"title": "bug", "severity": "high"}]}'
        issues = _extract_issues_array(json_str)
        assert len(issues) == 1
        assert issues[0]["title"] == "bug"

    def test_no_issues_key(self):
        issues = _extract_issues_array('{"summary": "ok"}')
        assert issues == []

    def test_empty_issues(self):
        issues = _extract_issues_array('{"issues": []}')
        assert issues == []


class TestTraeCLIClient:
    def setup_method(self):
        self.config = TraeClientConfig(trae_cli_path="trae-cli", timeout=10)

    @patch("runtime.clients.trae.subprocess.run")
    def test_check_cli_available_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="trae-cli v1.0", stderr="")
        client = TraeCLIClient(self.config)
        assert client._check_cli_available() is True

    @patch("runtime.clients.trae.subprocess.run")
    def test_check_cli_not_found(self, mock_run):
        mock_run.side_effect = FileNotFoundError()
        client = TraeCLIClient.__new__(TraeCLIClient)
        client.config = self.config
        assert client._check_cli_available() is False

    def test_build_command_basic(self):
        client = TraeCLIClient.__new__(TraeCLIClient)
        client.config = TraeClientConfig(trae_cli_path="trae-cli", yolo=False)
        cmd = client._build_command("hello")
        assert "trae-cli" in cmd
        assert "-p" in cmd
        assert "--json" in cmd
        assert "hello" in cmd

    def test_build_command_with_yolo(self):
        client = TraeCLIClient.__new__(TraeCLIClient)
        client.config = TraeClientConfig(trae_cli_path="trae-cli", yolo=True)
        cmd = client._build_command("hello")
        assert "-y" in cmd

    def test_build_command_with_model(self):
        client = TraeCLIClient.__new__(TraeCLIClient)
        client.config = TraeClientConfig(trae_cli_path="trae-cli", model="gpt-4", yolo=False)
        cmd = client._build_command("hello")
        assert "-c" in cmd
        assert "model.name=gpt-4" in cmd

    def test_extract_content_message_format(self):
        client = TraeCLIClient.__new__(TraeCLIClient)
        client.config = self.config
        data = {"message": {"content": '{"issues": []}'}}
        content = client._extract_content(data)
        assert content == '{"issues": []}'

    def test_extract_content_strips_markdown(self):
        client = TraeCLIClient.__new__(TraeCLIClient)
        client.config = self.config
        data = {"message": {"content": "```json\n{}\n```"}}
        content = client._extract_content(data)
        assert content == "{}"

    def test_extract_content_empty_raises(self):
        client = TraeCLIClient.__new__(TraeCLIClient)
        client.config = self.config
        data = {"message": {"content": ""}}
        with pytest.raises(RuntimeError, match="空响应"):
            client._extract_content(data)

    def test_extract_content_fallback_keys(self):
        client = TraeCLIClient.__new__(TraeCLIClient)
        client.config = self.config
        data = {"response": "some response"}
        content = client._extract_content(data)
        assert content == "some response"

    def test_extract_content_unknown_format_raises(self):
        client = TraeCLIClient.__new__(TraeCLIClient)
        client.config = self.config
        with pytest.raises(RuntimeError):
            client._extract_content({"unknown_key": "value"})
