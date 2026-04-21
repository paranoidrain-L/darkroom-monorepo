# -*- coding: utf-8 -*-
"""Tracing bridge abstractions and OpenTelemetry adapter for P2.2."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from loguru import logger

from products.tech_blog_monitor.observability.events import StageEvent, StageOutcome, TaskResult
from products.tech_blog_monitor.observability.otlp import (
    DEFAULT_OTLP_EXPORT_TIMEOUT_MS,
    DEFAULT_OTLP_TIMEOUT_SECONDS,
    build_otlp_http_session,
    resolve_otlp_endpoint,
)


class TracingBridge(Protocol):
    def emit_stage_event(self, event: StageEvent) -> None: ...

    def emit_stage_outcome(self, outcome: StageOutcome) -> None: ...

    def emit_task_result(self, result: TaskResult) -> None: ...

    def emit_run_finished(self, summary: dict) -> None: ...


def _iso_to_ns(value: str) -> int:
    return int(datetime.fromisoformat(value).timestamp() * 1_000_000_000)


class NoopTracingBridge:
    def emit_stage_event(self, event: StageEvent) -> None:
        return None

    def emit_stage_outcome(self, outcome: StageOutcome) -> None:
        return None

    def emit_task_result(self, result: TaskResult) -> None:
        return None

    def emit_run_finished(self, summary: dict) -> None:
        return None


class OpenTelemetryTracingBridge(NoopTracingBridge):
    def __init__(
        self,
        *,
        service_name: str = "tech_blog_monitor",
        endpoint: str = "",
    ) -> None:
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        except Exception as exc:  # pragma: no cover - import guard
            raise RuntimeError(f"opentelemetry unavailable: {exc}") from exc

        resource = Resource.create({"service.name": service_name})
        self._provider = TracerProvider(resource=resource)
        self._session = build_otlp_http_session()
        resolved_endpoint = resolve_otlp_endpoint(endpoint, signal="traces")
        exporter = OTLPSpanExporter(
            endpoint=resolved_endpoint or None,
            timeout=DEFAULT_OTLP_TIMEOUT_SECONDS,
            session=self._session,
        )
        self._provider.add_span_processor(SimpleSpanProcessor(exporter))
        self._tracer = self._provider.get_tracer(service_name)
        self._active_stage_spans: dict[tuple[str, str, str], object] = {}
        self._closed = False

    def emit_stage_event(self, event: StageEvent) -> None:
        if event.event_type != "started":
            return
        span = self._tracer.start_span(
            name=f"stage:{event.stage_name}",
            start_time=_iso_to_ns(event.observed_at),
        )
        span.set_attribute("run_id", event.run_id)
        span.set_attribute("task_id", event.task_id)
        span.set_attribute("task_type", event.task_type)
        for key, value in event.dimensions.items():
            span.set_attribute(f"stage.{key}", str(value))
        self._active_stage_spans[(event.run_id, event.task_id, event.stage_name)] = span

    def emit_stage_outcome(self, outcome: StageOutcome) -> None:
        key = (outcome.run_id, outcome.task_id, outcome.stage_name)
        span = self._active_stage_spans.pop(key, None)
        if span is None:
            span = self._tracer.start_span(
                name=f"stage:{outcome.stage_name}",
                start_time=_iso_to_ns(outcome.started_at),
            )
        span.set_attribute("status", outcome.status)
        span.set_attribute("duration_ms", outcome.duration_ms)
        if outcome.error_code:
            span.set_attribute("error_code", outcome.error_code)
        if outcome.error_message:
            span.set_attribute("error_message", outcome.error_message)
        for key_name, value in outcome.dimensions.items():
            span.set_attribute(f"stage.{key_name}", str(value))
        span.end(end_time=_iso_to_ns(outcome.finished_at))

    def emit_task_result(self, result: TaskResult) -> None:
        span = self._tracer.start_span(
            name=f"task:{result.task_type}",
            start_time=_iso_to_ns(result.started_at),
        )
        span.set_attribute("run_id", result.run_id)
        span.set_attribute("task_id", result.task_id)
        span.set_attribute("status", result.status)
        span.set_attribute("duration_ms", result.duration_ms)
        if result.error_code:
            span.set_attribute("error_code", result.error_code)
        if result.error_message:
            span.set_attribute("error_message", result.error_message)
        for key, value in result.dimensions.items():
            span.set_attribute(f"task.{key}", str(value))
        span.end(end_time=_iso_to_ns(result.finished_at))

    def emit_run_finished(self, summary: dict) -> None:
        if self._closed:
            return
        try:
            self._provider.force_flush(timeout_millis=DEFAULT_OTLP_EXPORT_TIMEOUT_MS)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("otel force_flush 失败: {}", exc)
        finally:
            try:
                self._provider.shutdown(timeout_millis=DEFAULT_OTLP_EXPORT_TIMEOUT_MS)
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("otel shutdown 失败: {}", exc)
            finally:
                self._session.close()
                self._closed = True


class TracingObserver:
    def __init__(self, bridge: TracingBridge | None = None) -> None:
        self.bridge = bridge or NoopTracingBridge()

    def on_stage_event(self, event: StageEvent) -> None:
        self.bridge.emit_stage_event(event)

    def on_stage_outcome(self, outcome: StageOutcome) -> None:
        self.bridge.emit_stage_outcome(outcome)

    def on_task_result(self, result: TaskResult) -> None:
        self.bridge.emit_task_result(result)

    def on_run_finished(self, run_context, summary: dict) -> None:
        self.bridge.emit_run_finished(summary)


def build_tracing_bridge(
    *,
    exporter: str,
    endpoint: str,
    service_name: str = "tech_blog_monitor",
) -> TracingBridge:
    if exporter != "otlp":
        return NoopTracingBridge()
    return OpenTelemetryTracingBridge(service_name=service_name, endpoint=endpoint)
