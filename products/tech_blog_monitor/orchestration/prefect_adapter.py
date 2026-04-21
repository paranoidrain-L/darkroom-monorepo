# -*- coding: utf-8 -*-
"""Prefect adapter used as an optional orchestration backend."""

from __future__ import annotations

import asyncio
from inspect import isawaitable
from typing import Any, Callable
from uuid import uuid4

from products.tech_blog_monitor.config import TechBlogMonitorConfig
from products.tech_blog_monitor.orchestration.backend import SubmittedTask

PrefectSubmitter = Callable[[str, dict[str, Any], str], Any]


def _default_prefect_submitter(task_type: str, payload: dict[str, Any], deployment_name: str) -> Any:
    try:
        from prefect.deployments import run_deployment
    except Exception as exc:  # pragma: no cover - import guard
        raise RuntimeError(f"prefect runtime unavailable: {exc}") from exc

    return run_deployment(
        name=deployment_name,
        parameters={
            "task_type": task_type,
            **payload,
        },
    )


class PrefectOrchestrationBackend:
    backend_name = "prefect"

    def __init__(
        self,
        *,
        deployment_name: str,
        submitter: PrefectSubmitter | None = None,
    ) -> None:
        if not deployment_name.strip():
            raise RuntimeError("prefect deployment name is required")
        self.deployment_name = deployment_name.strip()
        self.submitter = submitter or _default_prefect_submitter

    def submit_monitor_run(
        self,
        config: TechBlogMonitorConfig,
        *,
        task_type: str,
        trigger_source: str,
        requested_by: str,
        input_payload_extra: dict[str, Any] | None = None,
    ) -> SubmittedTask:
        payload = {
            "output_path": config.output_path,
            "view": config.view,
            "incremental_mode": config.incremental_mode,
            "fetch_content": config.fetch_content,
            "asset_db_path": config.asset_db_path,
            "database_url": config.database_url,
            "observability_exporter": config.observability_exporter,
            "trigger_source": trigger_source,
            "requested_by": requested_by,
            **dict(input_payload_extra or {}),
        }
        submission = self.submitter(task_type, payload, self.deployment_name)
        if isawaitable(submission):
            submission = asyncio.run(submission)
        task_id = str(
            getattr(submission, "id", None)
            or getattr(submission, "flow_run_id", None)
            or getattr(submission, "name", None)
            or f"prefect_submission_{uuid4().hex[:8]}"
        )
        return SubmittedTask(
            task_id=task_id,
            task_type=task_type,
            backend_name=self.backend_name,
            accepted=True,
            metadata={
                "deployment_name": self.deployment_name,
                "submission_kind": submission.__class__.__name__,
            },
        )
