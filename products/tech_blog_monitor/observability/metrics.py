# -*- coding: utf-8 -*-
"""Metrics registry and observer adapters for P2.2."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from os import environ
from threading import Lock
from typing import Any

from loguru import logger

from products.tech_blog_monitor.observability.events import StageOutcome, TaskResult
from products.tech_blog_monitor.observability.otlp import (
    DEFAULT_OTLP_EXPORT_INTERVAL_MS,
    DEFAULT_OTLP_EXPORT_TIMEOUT_MS,
    DEFAULT_OTLP_TIMEOUT_SECONDS,
    build_otlp_http_session,
    resolve_otlp_endpoint,
)

_UTC = timezone.utc
_KNOWN_COUNTERS = (
    "feed_fetch_total",
    "feed_fetch_failures_total",
    "content_fetch_total",
    "content_low_quality_total",
    "enrichment_failures_total",
    "delivery_failures_total",
)
_KNOWN_HISTOGRAMS = (
    "run_duration_ms",
    "stage_duration_ms",
    "search_latency_ms",
    "qa_latency_ms",
    "insights_latency_ms",
)


def _utc_iso() -> str:
    return datetime.now(_UTC).isoformat()


@dataclass(frozen=True)
class MetricPoint:
    name: str
    metric_type: str
    value: float
    observed_at: str
    dimensions: dict[str, Any] = field(default_factory=dict)


class MetricsBridge:
    def emit(self, point: MetricPoint) -> None:
        return None

    def flush(self) -> None:
        return None

    def close(self) -> None:
        return None


class NoopMetricsBridge(MetricsBridge):
    pass


class OpenTelemetryMetricsBridge(NoopMetricsBridge):
    def __init__(
        self,
        *,
        service_name: str = "tech_blog_monitor",
        endpoint: str = "",
    ) -> None:
        try:
            from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
            from opentelemetry.sdk.metrics import MeterProvider
            from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
            from opentelemetry.sdk.resources import Resource
        except Exception as exc:  # pragma: no cover - import guard
            raise RuntimeError(f"opentelemetry metrics unavailable: {exc}") from exc

        resource = Resource.create({"service.name": service_name})
        self._session = build_otlp_http_session()
        resolved_endpoint = resolve_otlp_endpoint(endpoint, signal="metrics")
        exporter = OTLPMetricExporter(
            endpoint=resolved_endpoint or None,
            timeout=DEFAULT_OTLP_TIMEOUT_SECONDS,
            session=self._session,
        )
        reader = PeriodicExportingMetricReader(
            exporter,
            export_interval_millis=DEFAULT_OTLP_EXPORT_INTERVAL_MS,
            export_timeout_millis=DEFAULT_OTLP_EXPORT_TIMEOUT_MS,
        )
        self._provider = MeterProvider(resource=resource, metric_readers=[reader])
        self._meter = self._provider.get_meter(service_name)
        self._counters: dict[str, Any] = {}
        self._histograms: dict[str, Any] = {}
        self._closed = False

    def _counter(self, name: str):
        counter = self._counters.get(name)
        if counter is None:
            counter = self._meter.create_counter(name)
            self._counters[name] = counter
        return counter

    def _histogram(self, name: str):
        histogram = self._histograms.get(name)
        if histogram is None:
            histogram = self._meter.create_histogram(name)
            self._histograms[name] = histogram
        return histogram

    def emit(self, point: MetricPoint) -> None:
        attributes = {str(key): str(value) for key, value in point.dimensions.items()}
        if point.metric_type == "counter":
            self._counter(point.name).add(point.value, attributes=attributes)
            return
        self._histogram(point.name).record(point.value, attributes=attributes)

    def flush(self) -> None:
        if self._closed:
            return
        self._provider.force_flush(timeout_millis=DEFAULT_OTLP_EXPORT_TIMEOUT_MS)

    def close(self) -> None:
        if self._closed:
            return
        try:
            self.flush()
        finally:
            try:
                self._provider.shutdown(timeout_millis=DEFAULT_OTLP_EXPORT_TIMEOUT_MS)
            finally:
                self._session.close()
                self._closed = True


class MetricsRegistry:
    def __init__(self, bridge: MetricsBridge | None = None) -> None:
        self._lock = Lock()
        self._bridge = bridge or NoopMetricsBridge()
        self._counters: dict[str, float] = {name: 0.0 for name in _KNOWN_COUNTERS}
        self._histograms: dict[str, list[float]] = {name: [] for name in _KNOWN_HISTOGRAMS}
        self._points: list[MetricPoint] = []
        self._closed = False

    def _record_point(self, point: MetricPoint) -> None:
        self._points.append(point)
        if self._closed:
            return
        try:
            self._bridge.emit(point)
        except Exception as exc:
            logger.warning("metrics bridge emit 失败: {}", exc)

    def increment(
        self,
        name: str,
        value: float = 1.0,
        *,
        dimensions: dict[str, Any] | None = None,
    ) -> None:
        with self._lock:
            self._counters[name] = self._counters.get(name, 0.0) + value
            self._record_point(
                MetricPoint(
                    name=name,
                    metric_type="counter",
                    value=value,
                    observed_at=_utc_iso(),
                    dimensions=dict(dimensions or {}),
                )
            )

    def observe(
        self,
        name: str,
        value: float,
        *,
        dimensions: dict[str, Any] | None = None,
    ) -> None:
        with self._lock:
            bucket = self._histograms.setdefault(name, [])
            bucket.append(value)
            self._record_point(
                MetricPoint(
                    name=name,
                    metric_type="histogram",
                    value=value,
                    observed_at=_utc_iso(),
                    dimensions=dict(dimensions or {}),
                )
            )

    def observe_search_latency(self, value_ms: float, *, dimensions: dict[str, Any] | None = None) -> None:
        self.observe("search_latency_ms", value_ms, dimensions=dimensions)

    def observe_qa_latency(self, value_ms: float, *, dimensions: dict[str, Any] | None = None) -> None:
        self.observe("qa_latency_ms", value_ms, dimensions=dimensions)

    def observe_insights_latency(
        self,
        value_ms: float,
        *,
        dimensions: dict[str, Any] | None = None,
    ) -> None:
        self.observe("insights_latency_ms", value_ms, dimensions=dimensions)

    def flush(self) -> None:
        if self._closed:
            return
        try:
            self._bridge.flush()
        except Exception as exc:
            logger.warning("metrics bridge flush 失败: {}", exc)

    @property
    def closed(self) -> bool:
        return self._closed

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            try:
                self._bridge.close()
            except Exception as exc:
                logger.warning("metrics bridge close 失败: {}", exc)
            self._closed = True

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            counters = dict(self._counters)
            histograms = {
                name: {
                    "count": len(values),
                    "sum": sum(values),
                    "min": min(values) if values else 0.0,
                    "max": max(values) if values else 0.0,
                    "last": values[-1] if values else 0.0,
                }
                for name, values in self._histograms.items()
            }
            return {
                "counters": counters,
                "histograms": histograms,
                "points": [point.__dict__.copy() for point in self._points],
            }


_DEFAULT_REGISTRY: MetricsRegistry | None = None
_DEFAULT_REGISTRY_LOCK = Lock()


def build_metrics_bridge(
    *,
    exporter: str,
    endpoint: str,
    service_name: str = "tech_blog_monitor",
) -> MetricsBridge:
    if exporter != "otlp":
        return NoopMetricsBridge()
    return OpenTelemetryMetricsBridge(service_name=service_name, endpoint=endpoint)


def configure_default_metrics_registry(
    *,
    exporter: str | None = None,
    endpoint: str | None = None,
    service_name: str = "tech_blog_monitor",
) -> MetricsRegistry:
    resolved_exporter = exporter if exporter is not None else environ.get(
        "TECH_BLOG_OBSERVABILITY_EXPORTER",
        "none",
    )
    resolved_endpoint = endpoint if endpoint is not None else environ.get("TECH_BLOG_OTLP_ENDPOINT", "")

    try:
        bridge = build_metrics_bridge(
            exporter=resolved_exporter,
            endpoint=resolved_endpoint,
            service_name=service_name,
        )
    except Exception as exc:
        logger.warning("metrics bridge 初始化失败，降级为本地 registry: {}", exc)
        bridge = NoopMetricsBridge()
    registry = MetricsRegistry(bridge=bridge)

    global _DEFAULT_REGISTRY
    previous_registry: MetricsRegistry | None = None
    with _DEFAULT_REGISTRY_LOCK:
        previous_registry = _DEFAULT_REGISTRY
        _DEFAULT_REGISTRY = registry
    if previous_registry is not None and previous_registry is not registry:
        previous_registry.close()
    return registry


def reset_default_metrics_registry() -> MetricsRegistry:
    return configure_default_metrics_registry(exporter="none", endpoint="")


def get_default_metrics_registry() -> MetricsRegistry:
    global _DEFAULT_REGISTRY
    with _DEFAULT_REGISTRY_LOCK:
        registry = _DEFAULT_REGISTRY
    if registry is None or registry.closed:
        return configure_default_metrics_registry()
    return registry


class MetricsObserver:
    def __init__(self, registry: MetricsRegistry | None = None) -> None:
        self.registry = registry or get_default_metrics_registry()

    def on_stage_outcome(self, outcome: StageOutcome) -> None:
        self.registry.observe(
            "stage_duration_ms",
            outcome.duration_ms,
            dimensions={
                "stage_name": outcome.stage_name,
                "status": outcome.status,
            },
        )

    def on_task_result(self, result: TaskResult) -> None:
        if result.task_type == "fetch_feed":
            self.registry.increment(
                "feed_fetch_total",
                dimensions={"status": result.status},
            )
            if result.status != "success":
                self.registry.increment(
                    "feed_fetch_failures_total",
                    dimensions={"status": result.status},
                )

    def on_run_finished(self, run_context: Any, summary: dict[str, Any]) -> None:
        self.registry.observe("run_duration_ms", summary.get("duration_ms", 0))

        content_counts = summary.get("content_status_counts", {})
        content_total = sum(
            count for status, count in content_counts.items() if status != "not_fetched"
        )
        if content_total:
            self.registry.increment("content_fetch_total", content_total)
        low_quality_total = content_counts.get("low_quality", 0)
        if low_quality_total:
            self.registry.increment("content_low_quality_total", low_quality_total)

        enrichment_failures = summary.get("enrichment_status_counts", {}).get("failed", 0)
        if enrichment_failures:
            self.registry.increment("enrichment_failures_total", enrichment_failures)

        delivery_counts = summary.get("delivery_status_counts", {})
        delivery_failures = sum(
            count
            for status, count in delivery_counts.items()
            if status not in {"delivered", ""}
        )
        if delivery_failures:
            self.registry.increment("delivery_failures_total", delivery_failures)
        self.registry.close()
