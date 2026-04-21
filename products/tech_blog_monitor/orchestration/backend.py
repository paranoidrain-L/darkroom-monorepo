# -*- coding: utf-8 -*-
"""Orchestration backend contracts for P2.4."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from products.tech_blog_monitor.config import TechBlogMonitorConfig


@dataclass(frozen=True)
class SubmittedTask:
    task_id: str
    task_type: str
    backend_name: str
    accepted: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


class OrchestrationBackend(Protocol):
    backend_name: str

    def submit_monitor_run(
        self,
        config: TechBlogMonitorConfig,
        *,
        task_type: str,
        trigger_source: str,
        requested_by: str,
        input_payload_extra: dict[str, Any] | None = None,
    ) -> SubmittedTask: ...
