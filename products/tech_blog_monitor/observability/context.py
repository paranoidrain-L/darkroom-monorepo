# -*- coding: utf-8 -*-
"""Run and task context helpers for structured observability."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, Iterator
from uuid import uuid4

from loguru import logger

from products.tech_blog_monitor.observability.events import StageEvent, StageOutcome, TaskResult
from products.tech_blog_monitor.observability.sinks import NoopObserver

_UTC = timezone.utc


def _utc_now() -> datetime:
    return datetime.now(_UTC)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _duration_ms(started_counter: float, finished_counter: float) -> int:
    return max(int((finished_counter - started_counter) * 1000), 0)


def _default_run_id() -> str:
    return f"run_{_utc_now().strftime('%Y%m%dT%H%M%S')}_{uuid4().hex[:8]}"


@dataclass
class TaskContext:
    run_context: "RunContext"
    task_id: str
    task_type: str
    dimensions: dict[str, Any] = field(default_factory=dict)
    started_at: str = field(init=False)
    _started_counter: float = field(init=False, repr=False)
    _completed: bool = field(default=False, init=False, repr=False)
    _result: TaskResult | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        started_dt = _utc_now()
        self.started_at = _iso(started_dt)
        self._started_counter = perf_counter()

    def complete(
        self,
        *,
        status: str,
        error_code: str = "",
        error_message: str = "",
        dimensions: dict[str, Any] | None = None,
    ) -> TaskResult:
        if self._completed:
            assert self._result is not None
            return self._result

        if dimensions:
            self.dimensions.update(dimensions)

        finished_dt = _utc_now()
        finished_counter = perf_counter()
        result = TaskResult(
            run_id=self.run_context.run_id,
            task_id=self.task_id,
            task_type=self.task_type,
            started_at=self.started_at,
            finished_at=_iso(finished_dt),
            duration_ms=_duration_ms(self._started_counter, finished_counter),
            status=status,
            error_code=error_code,
            error_message=error_message,
            dimensions=dict(self.dimensions),
        )
        self._completed = True
        self._result = result
        self.run_context.task_results.append(result)
        self.run_context._notify("on_task_result", result)
        return result


@dataclass
class RunContext:
    observer: Any = field(default_factory=NoopObserver)
    run_id: str = field(default_factory=_default_run_id)
    task_id: str = ""
    task_type: str = "monitor_run"
    dimensions: dict[str, Any] = field(default_factory=dict)
    started_at: str = field(init=False)
    stage_outcomes: list[StageOutcome] = field(default_factory=list)
    task_results: list[TaskResult] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    asset_run_id: str = ""
    observer_error_count: int = 0
    _started_counter: float = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.task_id:
            self.task_id = f"{self.run_id}:main"
        started_dt = _utc_now()
        self.started_at = _iso(started_dt)
        self._started_counter = perf_counter()
        self._notify("on_run_started", self)

    def _notify(self, method_name: str, *args: Any) -> None:
        try:
            getattr(self.observer, method_name)(*args)
        except Exception as exc:
            self.observer_error_count += 1
            logger.warning("observer {} 失败: {}", method_name, exc)

    @contextmanager
    def stage(
        self,
        stage_name: str,
        *,
        dimensions: dict[str, Any] | None = None,
    ) -> Iterator[None]:
        stage_dimensions = dict(dimensions or {})
        started_dt = _utc_now()
        started_counter = perf_counter()
        self._notify(
            "on_stage_event",
            StageEvent(
                run_id=self.run_id,
                task_id=self.task_id,
                task_type=self.task_type,
                stage_name=stage_name,
                event_type="started",
                observed_at=_iso(started_dt),
                dimensions=stage_dimensions,
            ),
        )
        try:
            yield
        except Exception as exc:
            self.record_stage_outcome(
                stage_name,
                status="failed",
                started_at=_iso(started_dt),
                started_counter=started_counter,
                error_code=exc.__class__.__name__,
                error_message=str(exc),
                dimensions=stage_dimensions,
            )
            raise
        else:
            self.record_stage_outcome(
                stage_name,
                status="success",
                started_at=_iso(started_dt),
                started_counter=started_counter,
                dimensions=stage_dimensions,
            )

    def record_stage_skip(
        self,
        stage_name: str,
        *,
        dimensions: dict[str, Any] | None = None,
    ) -> StageOutcome:
        started_dt = _utc_now()
        return self.record_stage_outcome(
            stage_name,
            status="skipped",
            started_at=_iso(started_dt),
            started_counter=perf_counter(),
            dimensions=dimensions or {},
        )

    def record_stage_outcome(
        self,
        stage_name: str,
        *,
        status: str,
        started_at: str,
        started_counter: float,
        error_code: str = "",
        error_message: str = "",
        dimensions: dict[str, Any] | None = None,
    ) -> StageOutcome:
        finished_dt = _utc_now()
        finished_counter = perf_counter()
        outcome = StageOutcome(
            run_id=self.run_id,
            task_id=self.task_id,
            task_type=self.task_type,
            stage_name=stage_name,
            started_at=started_at,
            finished_at=_iso(finished_dt),
            duration_ms=_duration_ms(started_counter, finished_counter),
            status=status,
            error_code=error_code,
            error_message=error_message,
            dimensions=dict(dimensions or {}),
        )
        self.stage_outcomes.append(outcome)
        self._notify(
            "on_stage_event",
            StageEvent(
                run_id=self.run_id,
                task_id=self.task_id,
                task_type=self.task_type,
                stage_name=stage_name,
                event_type="finished",
                observed_at=outcome.finished_at,
                dimensions={"status": status, **outcome.dimensions},
            ),
        )
        self._notify("on_stage_outcome", outcome)
        return outcome

    def start_task(
        self,
        *,
        task_id: str,
        task_type: str,
        dimensions: dict[str, Any] | None = None,
    ) -> TaskContext:
        return TaskContext(
            run_context=self,
            task_id=task_id,
            task_type=task_type,
            dimensions=dict(dimensions or {}),
        )

    def finish(
        self,
        *,
        status: str,
        summary: dict[str, Any],
        error_code: str = "",
        error_message: str = "",
    ) -> dict[str, Any]:
        base_summary = self.compose_summary(
            status=status,
            summary=summary,
            error_code=error_code,
            error_message=error_message,
        )
        self.summary = base_summary
        self._notify("on_run_finished", self, base_summary)
        return base_summary

    def compose_summary(
        self,
        *,
        status: str,
        summary: dict[str, Any],
        error_code: str = "",
        error_message: str = "",
    ) -> dict[str, Any]:
        finished_dt = _utc_now()
        finished_counter = perf_counter()
        base_summary = {
            "run_id": self.run_id,
            "asset_run_id": self.asset_run_id,
            "task_id": self.task_id,
            "task_type": self.task_type,
            "started_at": self.started_at,
            "finished_at": _iso(finished_dt),
            "duration_ms": _duration_ms(self._started_counter, finished_counter),
            "status": status,
            "error_code": error_code,
            "error_message": error_message,
            "observer_error_count": self.observer_error_count,
            "dimensions": dict(self.dimensions),
        }
        base_summary.update(summary)
        return base_summary
