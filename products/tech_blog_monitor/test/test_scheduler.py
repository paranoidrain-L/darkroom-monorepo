# -*- coding: utf-8 -*-
"""Scheduler and local orchestration tests for P2.4."""

from __future__ import annotations

from products.tech_blog_monitor.config import FeedSource, TechBlogMonitorConfig
from products.tech_blog_monitor.local_scheduler import run_job, start_local_scheduler
from products.tech_blog_monitor.orchestration import SubmittedTask


def _config(tmp_path, **kwargs) -> TechBlogMonitorConfig:
    defaults = {
        "feeds": [FeedSource("Dummy", "https://dummy.com/rss", "测试")],
        "output_path": str(tmp_path / "report.md"),
    }
    defaults.update(kwargs)
    return TechBlogMonitorConfig(**defaults)


def test_run_job_uses_local_backend_by_default(monkeypatch, tmp_path):
    config = _config(tmp_path)
    monkeypatch.setattr(
        TechBlogMonitorConfig,
        "from_env",
        classmethod(lambda cls: config),
    )

    def _fake_run_monitor(self, cfg, **kwargs):
        self.last_task_id = "task_scheduled_local"
        self.last_task_status = "succeeded"
        return 0

    monkeypatch.setattr(
        "products.tech_blog_monitor.orchestration.local_backend.LocalTaskRunner.run_monitor",
        _fake_run_monitor,
    )

    submission = run_job(str(tmp_path))

    assert submission.backend_name == "local"
    assert submission.task_id == "task_scheduled_local"
    assert submission.metadata["task_status"] == "succeeded"


def test_run_job_uses_injected_prefect_backend(monkeypatch, tmp_path):
    config = _config(tmp_path)
    monkeypatch.setattr(
        TechBlogMonitorConfig,
        "from_env",
        classmethod(lambda cls: config),
    )

    class DummyBackend:
        backend_name = "prefect"

        def submit_monitor_run(self, cfg, **kwargs):
            return SubmittedTask(
                task_id="prefect-flow-run-1",
                task_type=kwargs["task_type"],
                backend_name=self.backend_name,
                metadata={"deployment_name": "demo/deploy"},
            )

    submission = run_job(str(tmp_path), backend=DummyBackend())

    assert submission.backend_name == "prefect"
    assert submission.task_id == "prefect-flow-run-1"


def test_run_job_falls_back_to_local_when_prefect_submit_fails(monkeypatch, tmp_path):
    config = _config(tmp_path)
    monkeypatch.setattr(
        TechBlogMonitorConfig,
        "from_env",
        classmethod(lambda cls: config),
    )

    class FailingBackend:
        backend_name = "prefect"

        def submit_monitor_run(self, cfg, **kwargs):
            raise RuntimeError("prefect submit failed")

    def _fake_run_monitor(self, cfg, **kwargs):
        self.last_task_id = "task_scheduled_fallback"
        self.last_task_status = "succeeded"
        return 0

    monkeypatch.setattr(
        "products.tech_blog_monitor.orchestration.local_backend.LocalTaskRunner.run_monitor",
        _fake_run_monitor,
    )

    submission = run_job(str(tmp_path), backend=FailingBackend())

    assert submission.backend_name == "local"
    assert submission.task_id == "task_scheduled_fallback"
    assert submission.metadata["task_status"] == "succeeded"


def test_start_local_scheduler_registers_jobs(monkeypatch, tmp_path):
    config = _config(tmp_path)
    monkeypatch.setattr(
        TechBlogMonitorConfig,
        "from_env",
        classmethod(lambda cls: config),
    )
    captured: dict[str, object] = {"jobs": []}

    class FakeScheduler:
        def __init__(self, timezone):
            captured["timezone"] = timezone

        def add_job(self, func, trigger, kwargs, name, max_instances, misfire_grace_time):
            captured["jobs"].append(
                {
                    "func": func,
                    "kwargs": kwargs,
                    "name": name,
                    "max_instances": max_instances,
                    "misfire_grace_time": misfire_grace_time,
                }
            )

        def start(self):
            captured["started"] = True

        def shutdown(self, wait=False):
            captured["shutdown"] = wait

    monkeypatch.setattr("products.tech_blog_monitor.local_scheduler.BlockingScheduler", FakeScheduler)

    start_local_scheduler(["09:00", "18:00"], str(tmp_path))

    assert captured["started"] is True
    assert len(captured["jobs"]) == 2
    assert captured["jobs"][0]["func"] is run_job
    assert captured["jobs"][0]["kwargs"]["output_dir"] == str(tmp_path)
