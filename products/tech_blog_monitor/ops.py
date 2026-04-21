# -*- coding: utf-8 -*-
"""Operational summary helpers for P2.5."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any

from products.tech_blog_monitor.repository_provider import open_repository_bundle

_RUN_TASK_TYPES = ("manual_run", "scheduled_run")


def _safe_int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    return 0


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 4)


@dataclass(frozen=True)
class OperationalKPI:
    name: str
    value: float | None
    numerator: int
    denominator: int
    unit: str = "ratio"


@dataclass(frozen=True)
class FailureSample:
    task_id: str
    task_type: str
    task_status: str
    started_at: int
    error_code: str
    error_message: str


@dataclass(frozen=True)
class OperationalSummary:
    window_size: int
    task_status_counts: dict[str, int]
    task_type_counts: dict[str, int]
    kpis: list[OperationalKPI]
    recent_failures: list[FailureSample]
    latest_task_id: str
    latest_run_task_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "window_size": self.window_size,
            "task_status_counts": dict(self.task_status_counts),
            "task_type_counts": dict(self.task_type_counts),
            "kpis": [asdict(item) for item in self.kpis],
            "recent_failures": [asdict(item) for item in self.recent_failures],
            "latest_task_id": self.latest_task_id,
            "latest_run_task_id": self.latest_run_task_id,
        }


def build_operational_summary(
    asset_db_path: str,
    *,
    database_url: str = "",
    limit: int = 50,
) -> OperationalSummary:
    with open_repository_bundle(asset_db_path=asset_db_path, database_url=database_url) as bundle:
        tasks = bundle.task_repository.list_tasks(limit=limit)

    task_status_counts = Counter(task["task_status"] for task in tasks)
    task_type_counts = Counter(task["task_type"] for task in tasks)
    run_tasks = [task for task in tasks if task["task_type"] in _RUN_TASK_TYPES]

    run_successes = sum(1 for task in run_tasks if task["task_status"] == "succeeded")
    durations: list[int] = []
    feed_success_total = 0
    feed_failure_total = 0
    content_success_total = 0
    content_total = 0
    low_quality_total = 0
    enrichment_failure_total = 0
    enrichment_total = 0
    delivery_success_total = 0
    delivery_total = 0

    for task in run_tasks:
        result_payload = task.get("result_payload", {})
        run_summary = result_payload.get("run_summary", {})
        durations.append(_safe_int(run_summary.get("duration_ms")))

        feed_stats = run_summary.get("feed_stats", {})
        feed_success_total += _safe_int(feed_stats.get("success"))
        feed_failure_total += _safe_int(feed_stats.get("failure"))

        content_counts = run_summary.get("content_status_counts", {})
        content_success_total += _safe_int(content_counts.get("fetched"))
        low_quality_total += _safe_int(content_counts.get("low_quality"))
        content_total += sum(
            _safe_int(count)
            for status, count in content_counts.items()
            if status != "not_fetched"
        )

        enrichment_counts = run_summary.get("enrichment_status_counts", {})
        enrichment_failure_total += _safe_int(enrichment_counts.get("failed"))
        enrichment_total += sum(_safe_int(count) for count in enrichment_counts.values())

        delivery_counts = run_summary.get("delivery_status_counts", {})
        delivery_success_total += _safe_int(delivery_counts.get("delivered"))
        delivery_total += sum(_safe_int(count) for count in delivery_counts.values())

    mean_run_duration_ms = round(sum(durations) / len(durations), 2) if durations else None
    kpis = [
        OperationalKPI(
            name="run_success_rate",
            value=_ratio(run_successes, len(run_tasks)),
            numerator=run_successes,
            denominator=len(run_tasks),
        ),
        OperationalKPI(
            name="feed_availability",
            value=_ratio(feed_success_total, feed_success_total + feed_failure_total),
            numerator=feed_success_total,
            denominator=feed_success_total + feed_failure_total,
        ),
        OperationalKPI(
            name="content_extraction_pass_rate",
            value=_ratio(content_success_total, content_total),
            numerator=content_success_total,
            denominator=content_total,
        ),
        OperationalKPI(
            name="low_quality_ratio",
            value=_ratio(low_quality_total, content_total),
            numerator=low_quality_total,
            denominator=content_total,
        ),
        OperationalKPI(
            name="enrichment_failure_rate",
            value=_ratio(enrichment_failure_total, enrichment_total),
            numerator=enrichment_failure_total,
            denominator=enrichment_total,
        ),
        OperationalKPI(
            name="delivery_success_rate",
            value=_ratio(delivery_success_total, delivery_total),
            numerator=delivery_success_total,
            denominator=delivery_total,
        ),
        OperationalKPI(
            name="mean_run_duration_ms",
            value=mean_run_duration_ms,
            numerator=sum(durations),
            denominator=len(durations),
            unit="ms",
        ),
    ]

    recent_failures = [
        FailureSample(
            task_id=task["task_id"],
            task_type=task["task_type"],
            task_status=task["task_status"],
            started_at=_safe_int(task["started_at"]),
            error_code=task.get("error_code", ""),
            error_message=task.get("error_message", ""),
        )
        for task in tasks
        if task["task_status"] != "succeeded"
    ][:5]

    return OperationalSummary(
        window_size=len(tasks),
        task_status_counts=dict(task_status_counts),
        task_type_counts=dict(task_type_counts),
        kpis=kpis,
        recent_failures=recent_failures,
        latest_task_id=tasks[0]["task_id"] if tasks else "",
        latest_run_task_id=run_tasks[0]["task_id"] if run_tasks else "",
    )
