# -*- coding: utf-8 -*-
"""Local-first observer implementations for structured observability."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from threading import Lock
from typing import Any

from products.tech_blog_monitor.observability.events import StageEvent, StageOutcome, TaskResult


def _serialize(value: Any) -> Any:
    if is_dataclass(value):
        return {key: _serialize(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _serialize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize(item) for item in value]
    return value


class NoopObserver:
    def on_run_started(self, run_context: Any) -> None:
        return None

    def on_stage_event(self, event: StageEvent) -> None:
        return None

    def on_stage_outcome(self, outcome: StageOutcome) -> None:
        return None

    def on_task_result(self, result: TaskResult) -> None:
        return None

    def on_run_finished(self, run_context: Any, summary: dict[str, Any]) -> None:
        return None


class InMemoryObserver(NoopObserver):
    def __init__(self) -> None:
        self._lock = Lock()
        self.run_starts: list[dict[str, Any]] = []
        self.stage_events: list[StageEvent] = []
        self.stage_outcomes: list[StageOutcome] = []
        self.task_results: list[TaskResult] = []
        self.run_summaries: list[dict[str, Any]] = []

    def on_run_started(self, run_context: Any) -> None:
        with self._lock:
            self.run_starts.append(
                {
                    "run_id": run_context.run_id,
                    "task_id": run_context.task_id,
                    "task_type": run_context.task_type,
                    "started_at": run_context.started_at,
                    "dimensions": dict(run_context.dimensions),
                }
            )

    def on_stage_event(self, event: StageEvent) -> None:
        with self._lock:
            self.stage_events.append(event)

    def on_stage_outcome(self, outcome: StageOutcome) -> None:
        with self._lock:
            self.stage_outcomes.append(outcome)

    def on_task_result(self, result: TaskResult) -> None:
        with self._lock:
            self.task_results.append(result)

    def on_run_finished(self, run_context: Any, summary: dict[str, Any]) -> None:
        with self._lock:
            self.run_summaries.append(dict(summary))


class JsonlObserver(NoopObserver):
    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self._lock = Lock()

    def _append_record(self, record_type: str, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(
            {
                "record_type": record_type,
                "payload": _serialize(payload),
            },
            ensure_ascii=False,
        )
        with self._lock:
            with self.path.open("a", encoding="utf-8") as file:
                file.write(line + "\n")

    def on_run_started(self, run_context: Any) -> None:
        self._append_record(
            "run_started",
            {
                "run_id": run_context.run_id,
                "task_id": run_context.task_id,
                "task_type": run_context.task_type,
                "started_at": run_context.started_at,
                "dimensions": dict(run_context.dimensions),
            },
        )

    def on_stage_event(self, event: StageEvent) -> None:
        self._append_record("stage_event", _serialize(event))

    def on_stage_outcome(self, outcome: StageOutcome) -> None:
        self._append_record("stage_outcome", _serialize(outcome))

    def on_task_result(self, result: TaskResult) -> None:
        self._append_record("task_result", _serialize(result))

    def on_run_finished(self, run_context: Any, summary: dict[str, Any]) -> None:
        self._append_record("run_finished", summary)


class CompositeObserver(NoopObserver):
    def __init__(self, observers: list[Any] | tuple[Any, ...]) -> None:
        self.observers = [observer for observer in observers if observer is not None]

    def _dispatch(self, method_name: str, *args: Any) -> None:
        errors: list[str] = []
        for observer in self.observers:
            method = getattr(observer, method_name, None)
            if method is None:
                continue
            try:
                method(*args)
            except Exception as exc:
                errors.append(f"{observer.__class__.__name__}: {exc}")
        if errors:
            raise RuntimeError("; ".join(errors))

    def on_run_started(self, run_context: Any) -> None:
        self._dispatch("on_run_started", run_context)

    def on_stage_event(self, event: StageEvent) -> None:
        self._dispatch("on_stage_event", event)

    def on_stage_outcome(self, outcome: StageOutcome) -> None:
        self._dispatch("on_stage_outcome", outcome)

    def on_task_result(self, result: TaskResult) -> None:
        self._dispatch("on_task_result", result)

    def on_run_finished(self, run_context: Any, summary: dict[str, Any]) -> None:
        self._dispatch("on_run_finished", run_context, summary)
