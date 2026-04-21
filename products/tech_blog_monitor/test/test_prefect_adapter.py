# -*- coding: utf-8 -*-
"""Prefect adapter and backend selection tests for P2.4."""

from __future__ import annotations

from products.tech_blog_monitor.config import FeedSource, TechBlogMonitorConfig
from products.tech_blog_monitor.orchestration import (
    LocalOrchestrationBackend,
    PrefectOrchestrationBackend,
    build_orchestration_backend,
)


def _config(tmp_path, **kwargs) -> TechBlogMonitorConfig:
    defaults = {
        "feeds": [FeedSource("Dummy", "https://dummy.com/rss", "测试")],
        "output_path": str(tmp_path / "report.md"),
    }
    defaults.update(kwargs)
    return TechBlogMonitorConfig(**defaults)


def test_build_orchestration_backend_defaults_to_local(tmp_path):
    backend = build_orchestration_backend(_config(tmp_path))
    assert isinstance(backend, LocalOrchestrationBackend)


def test_build_orchestration_backend_falls_back_when_prefect_unavailable(tmp_path):
    backend = build_orchestration_backend(
        _config(tmp_path, orchestration_mode="prefect", prefect_deployment_name=""),
    )
    assert isinstance(backend, LocalOrchestrationBackend)


def test_prefect_backend_submits_monitor_run(tmp_path):
    called = {}
    config = _config(
        tmp_path,
        orchestration_mode="prefect",
        prefect_deployment_name="demo/tech-blog",
        asset_db_path="/tmp/assets.db",
    )

    def _submitter(task_type, payload, deployment_name):
        called["task_type"] = task_type
        called["payload"] = payload
        called["deployment_name"] = deployment_name
        return type("FlowRun", (), {"id": "flow-run-123"})()

    backend = PrefectOrchestrationBackend(
        deployment_name=config.prefect_deployment_name,
        submitter=_submitter,
    )
    submission = backend.submit_monitor_run(
        config,
        task_type="scheduled_run",
        trigger_source="scheduler",
        requested_by="scheduler",
        input_payload_extra={"scheduled_for": "2026-04-17T18:00:00+08:00"},
    )

    assert submission.backend_name == "prefect"
    assert submission.task_id == "flow-run-123"
    assert called["task_type"] == "scheduled_run"
    assert called["deployment_name"] == "demo/tech-blog"
    assert called["payload"]["asset_db_path"] == "/tmp/assets.db"
    assert called["payload"]["scheduled_for"] == "2026-04-17T18:00:00+08:00"


def test_prefect_backend_accepts_awaitable_submitter(tmp_path):
    config = _config(
        tmp_path,
        orchestration_mode="prefect",
        prefect_deployment_name="demo/tech-blog",
    )

    async def _submitter(task_type, payload, deployment_name):
        assert task_type == "scheduled_run"
        assert payload["trigger_source"] == "scheduler"
        assert deployment_name == "demo/tech-blog"
        return type("FlowRun", (), {"id": "flow-run-async"})()

    backend = PrefectOrchestrationBackend(
        deployment_name=config.prefect_deployment_name,
        submitter=_submitter,
    )

    submission = backend.submit_monitor_run(
        config,
        task_type="scheduled_run",
        trigger_source="scheduler",
        requested_by="scheduler",
    )

    assert submission.backend_name == "prefect"
    assert submission.task_id == "flow-run-async"
    assert submission.metadata["deployment_name"] == "demo/tech-blog"
