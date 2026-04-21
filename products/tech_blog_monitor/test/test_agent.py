# -*- coding: utf-8 -*-
"""Tech Blog Monitor agent 单元测试。"""

import pytest

from products.tech_blog_monitor.agent import _normalize_argv, main
from products.tech_blog_monitor.config import TechBlogMonitorConfig


def test_normalize_argv_inserts_run_for_root_options():
    assert _normalize_argv(["--output", "report.md"]) == ["run", "--output", "report.md"]
    assert _normalize_argv(["run", "--output", "report.md"]) == ["run", "--output", "report.md"]
    assert _normalize_argv(["serve", "--run-now"]) == ["serve", "--run-now"]
    assert _normalize_argv(["feedback", "list", "--db", "a.db"]) == ["feedback", "list", "--db", "a.db"]
    assert _normalize_argv(["task", "rebuild-search-index", "--db", "a.db"]) == [
        "task",
        "rebuild-search-index",
        "--db",
        "a.db",
    ]
    assert _normalize_argv(["ops", "summary", "--db", "a.db"]) == ["ops", "summary", "--db", "a.db"]


def test_main_defaults_to_run(monkeypatch, tmp_path):
    config = TechBlogMonitorConfig(output_path="default.md")
    output_path = tmp_path / "report.md"
    captured = {}

    monkeypatch.setattr("sys.argv", ["agent.py", "--output", str(output_path), "--max-articles", "2"])
    monkeypatch.setattr(
        TechBlogMonitorConfig,
        "from_env",
        classmethod(lambda cls: config),
    )

    def _capture_run_monitor(self, cfg, **kwargs):
        captured["config"] = cfg
        captured["kwargs"] = kwargs
        return 0

    monkeypatch.setattr("products.tech_blog_monitor.tasks.LocalTaskRunner.run_monitor", _capture_run_monitor)

    with pytest.raises(SystemExit) as exc:
        main()

    assert exc.value.code == 0
    assert captured["config"].output_path == str(output_path)
    assert captured["config"].max_articles_per_feed == 2
    assert captured["kwargs"]["task_type"] == "manual_run"


def test_main_serve_mode_calls_scheduler(monkeypatch):
    calls = {"job": [], "start": []}

    monkeypatch.setattr(
        "sys.argv",
        ["agent.py", "serve", "--times", "09:00", "18:00", "--output-dir", "/tmp/reports", "--run-now"],
    )
    monkeypatch.setattr(
        "products.tech_blog_monitor.scheduler._job",
        lambda output_dir: calls["job"].append(output_dir),
    )
    monkeypatch.setattr(
        "products.tech_blog_monitor.scheduler.start",
        lambda times, output_dir: calls["start"].append((times, output_dir)),
    )

    main()

    assert calls["job"] == ["/tmp/reports"]
    assert calls["start"] == [(["09:00", "18:00"], "/tmp/reports")]


def test_main_feedback_mode_calls_feedback_cli(monkeypatch):
    called = {}
    monkeypatch.setattr(
        "sys.argv",
        ["agent.py", "feedback", "list", "--db", "/tmp/a.db"],
    )
    monkeypatch.setattr(
        "products.tech_blog_monitor.feedback_cli.main",
        lambda: called.setdefault("ok", True),
    )

    main()

    assert called["ok"] is True


def test_main_task_mode_calls_runner(monkeypatch):
    called = {}
    config = TechBlogMonitorConfig(output_path="default.md")
    monkeypatch.setattr(
        "sys.argv",
        ["agent.py", "task", "rebuild-search-index", "--db", "/tmp/assets.db"],
    )
    monkeypatch.setattr(
        TechBlogMonitorConfig,
        "from_env",
        classmethod(lambda cls: config),
    )

    def _capture_rebuild_search(self, **kwargs):
        called["kwargs"] = kwargs
        return {"documents_upserted": 1}

    monkeypatch.setattr("products.tech_blog_monitor.tasks.LocalTaskRunner.rebuild_search_index", _capture_rebuild_search)

    main()

    assert called["kwargs"]["asset_db_path"] == "/tmp/assets.db"
    assert called["kwargs"]["trigger_source"] == "cli"


def test_main_ops_summary_calls_ops_module(monkeypatch):
    called = {}
    config = TechBlogMonitorConfig(output_path="default.md", asset_db_path="/tmp/default.db")
    monkeypatch.setattr(
        "sys.argv",
        ["agent.py", "ops", "summary", "--db", "/tmp/assets.db", "--limit", "25"],
    )
    monkeypatch.setattr(
        TechBlogMonitorConfig,
        "from_env",
        classmethod(lambda cls: config),
    )

    class _Summary:
        def to_dict(self):
            return {"window_size": 1}

    def _capture_ops(asset_db_path, **kwargs):
        called["asset_db_path"] = asset_db_path
        called["kwargs"] = kwargs
        return _Summary()

    monkeypatch.setattr("products.tech_blog_monitor.ops.build_operational_summary", _capture_ops)

    main()

    assert called["asset_db_path"] == "/tmp/assets.db"
    assert called["kwargs"]["limit"] == 25


def test_main_ops_summary_uses_database_url_from_config(monkeypatch):
    called = {}
    config = TechBlogMonitorConfig(output_path="default.md", database_url="sqlite+pysqlite:////tmp/ops.db")
    monkeypatch.setattr(
        "sys.argv",
        ["agent.py", "ops", "summary", "--limit", "10"],
    )
    monkeypatch.setattr(
        TechBlogMonitorConfig,
        "from_env",
        classmethod(lambda cls: config),
    )

    class _Summary:
        def to_dict(self):
            return {"window_size": 0}

    def _capture_ops(asset_db_path, **kwargs):
        called["asset_db_path"] = asset_db_path
        called["kwargs"] = kwargs
        return _Summary()

    monkeypatch.setattr("products.tech_blog_monitor.ops.build_operational_summary", _capture_ops)

    main()

    assert called["asset_db_path"] == ""
    assert called["kwargs"]["database_url"] == "sqlite+pysqlite:////tmp/ops.db"
    assert called["kwargs"]["limit"] == 10
