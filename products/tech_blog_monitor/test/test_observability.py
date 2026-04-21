# -*- coding: utf-8 -*-
"""Tech Blog Monitor observability tests."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import products.tech_blog_monitor.observability as observability
from products.tech_blog_monitor.config import FeedSource, TechBlogMonitorConfig
from products.tech_blog_monitor.fetcher import Article, FeedHealth
from products.tech_blog_monitor.monitor import run
from products.tech_blog_monitor.observability import (
    CompositeObserver,
    InMemoryObserver,
    JsonlObserver,
    MetricsObserver,
    MetricsRegistry,
    NoopObserver,
    RunContext,
    StageEvent,
    StageOutcome,
    TaskResult,
    TracingObserver,
    configure_default_metrics_registry,
    get_default_metrics_registry,
    reset_default_metrics_registry,
)
from products.tech_blog_monitor.observability.metrics import NoopMetricsBridge
from products.tech_blog_monitor.observability.otlp import resolve_otlp_endpoint
from products.tech_blog_monitor.observability.tracing import NoopTracingBridge


def _article(url: str = "https://example.com/a") -> Article:
    return Article(
        title="Article A",
        url=url,
        source_name="Source A",
        category="行业风向标",
        source_id=f"Source A::{url}",
        rss_summary="raw summary",
        published=datetime(2026, 4, 10, tzinfo=timezone.utc),
        published_ts=1744243200,
        fetched_at=1744243200,
    )


def _config(tmp_path, **kwargs) -> TechBlogMonitorConfig:
    defaults = {
        "feeds": [FeedSource("Dummy", "https://dummy.com/rss", "测试")],
        "output_path": str(tmp_path / "report.md"),
    }
    defaults.update(kwargs)
    return TechBlogMonitorConfig(**defaults)


def _patch_success_chain(monkeypatch):
    health = [FeedHealth(name="Source A", url="https://example.com/feed", success=True, article_count=1)]
    monkeypatch.setattr(
        "products.tech_blog_monitor.monitor.fetch_all",
        lambda cfg, **kwargs: ([_article()], health),
    )
    monkeypatch.setattr(
        "products.tech_blog_monitor.monitor.fetch_contents",
        lambda items, workers, timeout, max_chars, **kwargs: [
            Article(
                **{
                    **item.__dict__,
                    "content_status": "fetched",
                    "content_source": "trafilatura",
                    "clean_text": "structured content",
                    "content_final_url": item.url,
                    "content_fetched_at": 1744243201,
                }
            )
            for item in items
        ],
    )
    monkeypatch.setattr(
        "products.tech_blog_monitor.monitor.analyze",
        lambda items, backend: (
            [
                Article(
                    **{
                        **item.__dict__,
                        "enrichment_status": "enriched",
                        "one_line_summary": "摘要",
                    }
                )
                for item in items
            ],
            "热点内容",
        ),
    )
    monkeypatch.setattr(
        "products.tech_blog_monitor.monitor.build_report",
        lambda items, trend_md, health_list, **kwargs: f"report for {len(items)} articles",
    )


def test_event_models_preserve_structured_fields():
    event = StageEvent(
        run_id="run-1",
        task_id="run-1:main",
        task_type="monitor_run",
        stage_name="fetch_feeds",
        event_type="started",
        observed_at="2026-04-20T00:00:00+00:00",
        dimensions={"source_type": "rss"},
    )
    outcome = StageOutcome(
        run_id="run-1",
        task_id="run-1:main",
        task_type="monitor_run",
        stage_name="fetch_feeds",
        started_at="2026-04-20T00:00:00+00:00",
        finished_at="2026-04-20T00:00:01+00:00",
        duration_ms=1000,
        status="success",
        dimensions={"article_count": 1},
    )
    result = TaskResult(
        run_id="run-1",
        task_id="run-1:feed:source-a",
        task_type="fetch_feed",
        started_at="2026-04-20T00:00:00+00:00",
        finished_at="2026-04-20T00:00:01+00:00",
        duration_ms=1000,
        status="success",
        dimensions={"source_name": "Source A"},
    )

    assert event.dimensions["source_type"] == "rss"
    assert outcome.duration_ms == 1000
    assert result.task_type == "fetch_feed"


def test_observability_package_exports_p2_2_symbols():
    assert "RunContext" in observability.__all__
    assert "JsonlObserver" in observability.__all__
    assert "MetricsObserver" in observability.__all__
    assert "TracingObserver" in observability.__all__
    assert "configure_default_metrics_registry" in observability.__all__


def test_metrics_registry_snapshot_and_fail_open_bridge():
    class FailingBridge(NoopMetricsBridge):
        def __init__(self) -> None:
            self.flush_called = 0
            self.close_called = 0

        def emit(self, point) -> None:
            raise RuntimeError(f"emit failed for {point.name}")

        def flush(self) -> None:
            self.flush_called += 1
            raise RuntimeError("flush failed")

        def close(self) -> None:
            self.close_called += 1
            raise RuntimeError("close failed")

    bridge = FailingBridge()
    registry = MetricsRegistry(bridge=bridge)

    registry.increment("feed_fetch_total")
    registry.observe("run_duration_ms", 12.0)
    registry.flush()
    registry.close()

    snapshot = registry.snapshot()
    assert snapshot["counters"]["feed_fetch_total"] == 1.0
    assert snapshot["histograms"]["run_duration_ms"]["count"] == 1
    assert bridge.flush_called == 1
    assert bridge.close_called == 1


def test_tracing_observer_lifecycle_uses_bridge():
    class RecordingTracingBridge(NoopTracingBridge):
        def __init__(self) -> None:
            self.events = []
            self.outcomes = []
            self.tasks = []
            self.finished = []

        def emit_stage_event(self, event) -> None:
            self.events.append(event.stage_name)

        def emit_stage_outcome(self, outcome) -> None:
            self.outcomes.append((outcome.stage_name, outcome.status))

        def emit_task_result(self, result) -> None:
            self.tasks.append((result.task_type, result.status))

        def emit_run_finished(self, summary: dict) -> None:
            self.finished.append(summary["status"])

    bridge = RecordingTracingBridge()
    observer = TracingObserver(bridge)
    run_context = RunContext(observer=observer)

    with run_context.stage("fetch_feeds"):
        pass
    task = run_context.start_task(task_id=f"{run_context.run_id}:task", task_type="fetch_feed")
    task.complete(status="success")
    run_context.finish(status="success", summary={"stage_timings": {}})

    assert bridge.events == ["fetch_feeds", "fetch_feeds"]
    assert bridge.outcomes == [("fetch_feeds", "success")]
    assert bridge.tasks == [("fetch_feed", "success")]
    assert bridge.finished == ["success"]


def test_noop_observer_allows_manual_run_context():
    run_context = RunContext(observer=NoopObserver())
    with run_context.stage("fetch_feeds"):
        pass
    task = run_context.start_task(task_id=f"{run_context.run_id}:task", task_type="fetch_feed")
    task.complete(status="success", dimensions={"article_count": 1})
    summary = run_context.finish(
        status="success",
        summary={"stage_timings": {"fetch_feeds": {"status": "success"}}},
    )
    assert summary["status"] == "success"


def test_jsonl_observer_writes_records(tmp_path):
    path = tmp_path / "observability.jsonl"
    observer = JsonlObserver(str(path))
    run_context = RunContext(observer=observer)
    with run_context.stage("fetch_feeds"):
        pass
    task = run_context.start_task(task_id=f"{run_context.run_id}:task", task_type="fetch_feed")
    task.complete(status="success")
    run_context.finish(status="success", summary={"stage_timings": {}})

    lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    record_types = [line["record_type"] for line in lines]
    assert "run_started" in record_types
    assert "stage_event" in record_types
    assert "stage_outcome" in record_types
    assert "task_result" in record_types
    assert "run_finished" in record_types


def test_run_context_records_failed_and_skipped_stages():
    observer = InMemoryObserver()
    run_context = RunContext(observer=observer)

    try:
        with run_context.stage("fetch_content"):
            raise RuntimeError("content failed")
    except RuntimeError:
        pass

    run_context.record_stage_skip("dispatch_deliveries", dimensions={"reason": "not_configured"})
    summary = run_context.finish(
        status="failed",
        summary={"stage_timings": {}},
        error_code="RuntimeError",
        error_message="content failed",
    )

    statuses = {outcome.stage_name: outcome.status for outcome in observer.stage_outcomes}
    assert statuses["fetch_content"] == "failed"
    assert statuses["dispatch_deliveries"] == "skipped"
    assert summary["status"] == "failed"


def test_run_emits_structured_summary(monkeypatch, tmp_path):
    observer = InMemoryObserver()
    json_path = tmp_path / "output.json"
    _patch_success_chain(monkeypatch)
    config = _config(tmp_path, json_output_path=str(json_path), fetch_content=True)

    exit_code = run(config, observer=observer)

    assert exit_code == 0
    assert observer.run_summaries[0]["feed_stats"]["success"] == 1
    assert observer.run_summaries[0]["content_status_counts"]["fetched"] == 1
    assert observer.run_summaries[0]["enrichment_status_counts"]["enriched"] == 1
    assert observer.run_summaries[0]["stage_timings"]["fetch_feeds"]["status"] == "success"
    assert observer.run_summaries[0]["stage_timings"]["archive_assets"]["status"] == "skipped"
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["run_summary"]["stage_timings"]["dispatch_deliveries"]["status"] == "skipped"


def test_run_records_failure_summary_when_no_articles(monkeypatch, tmp_path):
    observer = InMemoryObserver()
    config = _config(tmp_path)
    monkeypatch.setattr("products.tech_blog_monitor.monitor.fetch_all", lambda cfg, **kwargs: ([], []))

    exit_code = run(config, observer=observer)

    assert exit_code == 1
    assert observer.run_summaries[0]["status"] == "failed"
    assert observer.run_summaries[0]["error_code"] == "NoArticles"
    assert observer.run_summaries[0]["stage_timings"]["fetch_content"]["status"] == "skipped"


def test_metrics_observer_collects_run_metrics(monkeypatch, tmp_path):
    registry = MetricsRegistry()
    observer = CompositeObserver([InMemoryObserver(), MetricsObserver(registry)])
    health = [FeedHealth(name="Source A", url="https://example.com/feed", success=True, article_count=1)]

    def _fetch_all(cfg, **kwargs):
        run_context = kwargs.get("run_context")
        if run_context is not None:
            task = run_context.start_task(
                task_id=f"{run_context.run_id}:feed:Source A",
                task_type="fetch_feed",
                dimensions={"source_name": "Source A"},
            )
            task.complete(status="success", dimensions={"article_count": 1})
        return ([_article()], health)

    monkeypatch.setattr("products.tech_blog_monitor.monitor.fetch_all", _fetch_all)
    monkeypatch.setattr(
        "products.tech_blog_monitor.monitor.fetch_contents",
        lambda items, workers, timeout, max_chars, **kwargs: [
            Article(
                **{
                    **item.__dict__,
                    "content_status": "fetched",
                    "content_source": "trafilatura",
                    "clean_text": "structured content",
                    "content_final_url": item.url,
                    "content_fetched_at": 1744243201,
                }
            )
            for item in items
        ],
    )
    monkeypatch.setattr(
        "products.tech_blog_monitor.monitor.analyze",
        lambda items, backend: (items, "热点内容"),
    )
    monkeypatch.setattr(
        "products.tech_blog_monitor.monitor.build_report",
        lambda items, trend_md, health_list, **kwargs: f"report for {len(items)} articles",
    )
    config = _config(tmp_path, fetch_content=True)

    exit_code = run(config, observer=observer)

    assert exit_code == 0
    snapshot = registry.snapshot()
    assert snapshot["counters"]["feed_fetch_total"] == 1.0
    assert snapshot["counters"]["content_fetch_total"] == 1.0
    assert snapshot["histograms"]["run_duration_ms"]["count"] == 1
    assert snapshot["histograms"]["stage_duration_ms"]["count"] >= 1
    assert "search_latency_ms" in snapshot["histograms"]
    assert "qa_latency_ms" in snapshot["histograms"]


def test_observer_failure_does_not_block_run(monkeypatch, tmp_path):
    class FailingObserver(NoopObserver):
        def on_stage_event(self, event):
            raise RuntimeError("observer down")

    _patch_success_chain(monkeypatch)
    config = _config(tmp_path)

    exit_code = run(config, observer=FailingObserver())

    assert exit_code == 0


def test_config_validation_errors_emit_single_run_summary(tmp_path):
    observer = InMemoryObserver()
    config = _config(tmp_path, max_articles_per_feed=0, fetch_workers=0)

    exit_code = run(config, observer=observer)

    assert exit_code == 1
    assert len(observer.run_summaries) == 1
    assert observer.run_summaries[0]["status"] == "failed"
    assert observer.run_summaries[0]["error_code"] == "ConfigValidationError"


def test_otlp_init_failure_falls_back_to_local_jsonl(monkeypatch, tmp_path):
    jsonl_path = tmp_path / "observability.jsonl"
    _patch_success_chain(monkeypatch)
    monkeypatch.setattr(
        "products.tech_blog_monitor.monitor.build_tracing_bridge",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("collector unavailable")),
    )
    config = _config(
        tmp_path,
        observability_exporter="otlp",
        observability_jsonl_path=str(jsonl_path),
    )

    exit_code = run(config)

    assert exit_code == 0
    records = [json.loads(line) for line in jsonl_path.read_text(encoding="utf-8").splitlines()]
    assert any(record["record_type"] == "run_finished" for record in records)


def test_metrics_exporter_init_failure_falls_back_to_local_registry(monkeypatch):
    reset_default_metrics_registry()
    monkeypatch.setattr(
        "products.tech_blog_monitor.observability.metrics.build_metrics_bridge",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("metrics collector unavailable")),
    )

    registry = configure_default_metrics_registry(exporter="otlp", endpoint="http://127.0.0.1:4318")
    registry.increment("feed_fetch_total")

    snapshot = registry.snapshot()
    assert snapshot["counters"]["feed_fetch_total"] == 1.0


def test_closed_default_registry_is_recreated():
    registry = reset_default_metrics_registry()
    registry.close()

    recreated = get_default_metrics_registry()

    assert recreated is not registry
    assert recreated.closed is False


def test_replacing_default_registry_closes_previous(monkeypatch):
    class ClosingBridge(NoopMetricsBridge):
        def __init__(self) -> None:
            self.closed_count = 0

        def close(self) -> None:
            self.closed_count += 1

    bridge = ClosingBridge()
    previous = MetricsRegistry(bridge=bridge)
    monkeypatch.setattr(
        "products.tech_blog_monitor.observability.metrics._DEFAULT_REGISTRY",
        previous,
    )

    current = configure_default_metrics_registry(exporter="none", endpoint="")

    assert current is not previous
    assert previous.closed is True
    assert bridge.closed_count == 1


def test_resolve_otlp_endpoint_by_signal():
    assert resolve_otlp_endpoint("http://127.0.0.1:4318", signal="traces") == (
        "http://127.0.0.1:4318/v1/traces"
    )
    assert resolve_otlp_endpoint("http://127.0.0.1:4318", signal="metrics") == (
        "http://127.0.0.1:4318/v1/metrics"
    )
    assert resolve_otlp_endpoint("http://127.0.0.1:4318/v1/traces", signal="metrics") == (
        "http://127.0.0.1:4318/v1/metrics"
    )
    assert resolve_otlp_endpoint("http://127.0.0.1:4318/custom", signal="traces") == (
        "http://127.0.0.1:4318/custom/v1/traces"
    )
