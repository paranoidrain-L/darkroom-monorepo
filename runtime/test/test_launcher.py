# -*- coding: utf-8 -*-
"""
runtime.launcher 单元测试
"""

from unittest.mock import MagicMock, patch

from runtime.launcher import SUPPORTED_RUNTIMES, build_runtime_command, run_skill_runtime


class TestBuildRuntimeCommand:
    def test_supported_runtimes(self):
        assert SUPPORTED_RUNTIMES == ("claude_code", "trae", "codex")

    def test_build_claude_code_command(self):
        cmd = build_runtime_command(
            "claude_code",
            skill_prompt="执行 lint-fix skill",
            codex_prompt="unused",
        )
        assert cmd == [
            "claude",
            "-p",
            "执行 lint-fix skill",
            "--dangerously-skip-permissions",
            "--output-format",
            "json",
            "--no-session-persistence",
        ]

    def test_build_trae_command(self):
        cmd = build_runtime_command(
            "trae",
            skill_prompt="执行 code-review skill",
            codex_prompt="unused",
        )
        assert cmd == ["trae", "-p", "执行 code-review skill"]

    def test_build_codex_command(self):
        cmd = build_runtime_command(
            "codex",
            skill_prompt="unused",
            codex_prompt="请执行 code-review skill",
        )
        assert cmd == [
            "codex",
            "--sandbox",
            "workspace-write",
            "--ask-for-approval",
            "never",
            "exec",
            "--color",
            "never",
            "请执行 code-review skill",
        ]

    def test_build_unknown_runtime_raises(self):
        try:
            build_runtime_command("python", skill_prompt="x", codex_prompt="y")
            assert False, "expected ValueError"
        except ValueError as exc:
            assert "未知 AGENT_RUNTIME" in str(exc)


class TestRunSkillRuntime:
    @patch("runtime.launcher.subprocess.run")
    def test_run_skill_runtime_executes_command(self, mock_run):
        mock_run.return_value = MagicMock(returncode=7)

        result = run_skill_runtime(
            "trae",
            skill_prompt="执行 issue-monitor skill",
            codex_prompt="unused",
        )

        assert result == 7
        mock_run.assert_called_once_with(["trae", "-p", "执行 issue-monitor skill"])

    @patch("runtime.launcher.subprocess.run")
    def test_run_skill_runtime_unknown_runtime_returns_one(self, mock_run):
        result = run_skill_runtime(
            "python",
            skill_prompt="unused",
            codex_prompt="unused",
        )

        assert result == 1
        mock_run.assert_not_called()
