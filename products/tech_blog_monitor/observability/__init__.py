# -*- coding: utf-8 -*-
"""Observability building blocks for tech_blog_monitor."""

from products.tech_blog_monitor.observability.context import RunContext, TaskContext
from products.tech_blog_monitor.observability.events import StageEvent, StageOutcome, TaskResult
from products.tech_blog_monitor.observability.metrics import (
    MetricPoint,
    MetricsBridge,
    MetricsObserver,
    MetricsRegistry,
    NoopMetricsBridge,
    OpenTelemetryMetricsBridge,
    build_metrics_bridge,
    configure_default_metrics_registry,
    get_default_metrics_registry,
    reset_default_metrics_registry,
)
from products.tech_blog_monitor.observability.sinks import (
    CompositeObserver,
    InMemoryObserver,
    JsonlObserver,
    NoopObserver,
)
from products.tech_blog_monitor.observability.tracing import (
    NoopTracingBridge,
    OpenTelemetryTracingBridge,
    TracingBridge,
    TracingObserver,
    build_tracing_bridge,
)

__all__ = [
    "CompositeObserver",
    "InMemoryObserver",
    "JsonlObserver",
    "MetricPoint",
    "MetricsBridge",
    "MetricsObserver",
    "MetricsRegistry",
    "NoopMetricsBridge",
    "NoopObserver",
    "OpenTelemetryMetricsBridge",
    "NoopTracingBridge",
    "OpenTelemetryTracingBridge",
    "RunContext",
    "StageEvent",
    "StageOutcome",
    "TaskContext",
    "TaskResult",
    "TracingBridge",
    "TracingObserver",
    "build_metrics_bridge",
    "build_tracing_bridge",
    "configure_default_metrics_registry",
    "get_default_metrics_registry",
    "reset_default_metrics_registry",
]
