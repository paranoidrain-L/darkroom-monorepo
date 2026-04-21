# -*- coding: utf-8 -*-
"""Local orchestration backend backed by LocalTaskRunner."""

from __future__ import annotations

from products.tech_blog_monitor.config import TechBlogMonitorConfig
from products.tech_blog_monitor.orchestration.backend import SubmittedTask
from products.tech_blog_monitor.tasks import LocalTaskRunner


class LocalOrchestrationBackend:
    backend_name = "local"

    def submit_monitor_run(
        self,
        config: TechBlogMonitorConfig,
        *,
        task_type: str,
        trigger_source: str,
        requested_by: str,
        input_payload_extra: dict[str, object] | None = None,
    ) -> SubmittedTask:
        runner = LocalTaskRunner(config)
        exit_code = runner.run_monitor(
            config,
            task_type=task_type,
            trigger_source=trigger_source,
            requested_by=requested_by,
            input_payload_extra=input_payload_extra,
        )
        return SubmittedTask(
            task_id=runner.last_task_id,
            task_type=task_type,
            backend_name=self.backend_name,
            accepted=True,
            metadata={
                "exit_code": exit_code,
                "task_status": runner.last_task_status,
            },
        )
