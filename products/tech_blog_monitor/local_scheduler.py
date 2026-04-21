# -*- coding: utf-8 -*-
"""Local APScheduler path for tech_blog_monitor."""

from __future__ import annotations

import signal
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger

from products.tech_blog_monitor.config import TechBlogMonitorConfig
from products.tech_blog_monitor.orchestration import (
    LocalOrchestrationBackend,
    OrchestrationBackend,
    SubmittedTask,
    build_orchestration_backend,
)

_CST = timezone(timedelta(hours=8))
_DEFAULT_TIMES = ["09:00"]
_DEFAULT_OUTPUT_DIR = "reports/tech_blog"


def _make_output_path(output_dir: str) -> str:
    now = datetime.now(_CST)
    filename = now.strftime("tech_blog_%Y%m%d_%H%M.md")
    return str(Path(output_dir) / filename)


def _build_scheduled_config(output_dir: str) -> TechBlogMonitorConfig:
    output_path = _make_output_path(output_dir)
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    config = TechBlogMonitorConfig.from_env()
    config.output_path = output_path
    if not config.state_path:
        config.state_path = str(Path(output_dir) / "seen_articles.json")
    if not config.asset_db_path:
        config.asset_db_path = str(Path(output_dir) / "tech_blog_assets.db")
    return config


def run_job(
    output_dir: str,
    *,
    backend: OrchestrationBackend | None = None,
) -> SubmittedTask:
    config = _build_scheduled_config(output_dir)
    selected_backend = backend or build_orchestration_backend(config)
    logger.info(
        "触发 Tech Blog Monitor，报告路径: {}，orchestration={}",
        config.output_path,
        selected_backend.backend_name,
    )
    scheduled_for = datetime.now(_CST).isoformat()
    try:
        submitted = selected_backend.submit_monitor_run(
            config,
            task_type="scheduled_run",
            trigger_source="scheduler",
            requested_by="scheduler",
            input_payload_extra={"scheduled_for": scheduled_for},
        )
    except Exception as exc:
        if isinstance(selected_backend, LocalOrchestrationBackend):
            raise
        logger.warning("orchestration backend 提交失败，降级为 local: {}", exc)
        fallback_backend = LocalOrchestrationBackend()
        submitted = fallback_backend.submit_monitor_run(
            config,
            task_type="scheduled_run",
            trigger_source="scheduler",
            requested_by="scheduler",
            input_payload_extra={"scheduled_for": scheduled_for},
        )
        selected_backend = fallback_backend
    if isinstance(selected_backend, LocalOrchestrationBackend):
        exit_code = int(submitted.metadata.get("exit_code", 0))
        if exit_code != 0:
            logger.error("Tech Blog Monitor 执行失败，exit code: {}", exit_code)
    else:
        logger.info(
            "已提交 orchestration 任务: backend={} task_id={} deployment={}",
            submitted.backend_name,
            submitted.task_id,
            submitted.metadata.get("deployment_name", ""),
        )
    return submitted


def _parse_times(times: List[str]) -> List[tuple[int, int]]:
    result = []
    for t in times:
        try:
            h, m = t.strip().split(":")
            result.append((int(h), int(m)))
        except ValueError:
            logger.error("时间格式错误（应为 HH:MM）: {}", t)
            sys.exit(1)
    return result


def start_local_scheduler(
    times: List[str],
    output_dir: str,
    *,
    backend: OrchestrationBackend | None = None,
) -> None:
    config = TechBlogMonitorConfig.from_env()
    errors = config.validate()
    if errors:
        for e in errors:
            logger.error("配置错误: {}", e)
        sys.exit(1)

    scheduler = BlockingScheduler(timezone=_CST)
    parsed = _parse_times(times)
    for hour, minute in parsed:
        scheduler.add_job(
            run_job,
            trigger=CronTrigger(hour=hour, minute=minute, timezone=_CST),
            kwargs={"output_dir": output_dir, "backend": backend},
            name=f"tech-blog-{hour:02d}{minute:02d}",
            max_instances=1,
            misfire_grace_time=300,
        )
        logger.info("已注册触发时间: {:02d}:{:02d} CST", hour, minute)

    logger.info("报告目录: {}", Path(output_dir).resolve())
    logger.info("Tech Blog Monitor Local Scheduler 已启动，Ctrl+C 退出")

    def _shutdown(signum, frame):
        logger.info("收到退出信号，正在停止调度器...")
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)
    scheduler.start()
