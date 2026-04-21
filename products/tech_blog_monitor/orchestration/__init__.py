# -*- coding: utf-8 -*-
"""Orchestration backends for P2.4."""

from __future__ import annotations

from loguru import logger

from products.tech_blog_monitor.config import TechBlogMonitorConfig
from products.tech_blog_monitor.orchestration.backend import OrchestrationBackend, SubmittedTask
from products.tech_blog_monitor.orchestration.local_backend import LocalOrchestrationBackend
from products.tech_blog_monitor.orchestration.prefect_adapter import (
    PrefectOrchestrationBackend,
    PrefectSubmitter,
)


def build_orchestration_backend(
    config: TechBlogMonitorConfig,
    *,
    prefect_submitter: PrefectSubmitter | None = None,
) -> OrchestrationBackend:
    if config.orchestration_mode != "prefect":
        return LocalOrchestrationBackend()
    try:
        return PrefectOrchestrationBackend(
            deployment_name=config.prefect_deployment_name,
            submitter=prefect_submitter,
        )
    except Exception as exc:
        logger.warning("prefect backend 初始化失败，降级为 local: {}", exc)
        return LocalOrchestrationBackend()


__all__ = [
    "LocalOrchestrationBackend",
    "OrchestrationBackend",
    "PrefectOrchestrationBackend",
    "PrefectSubmitter",
    "SubmittedTask",
    "build_orchestration_backend",
]
