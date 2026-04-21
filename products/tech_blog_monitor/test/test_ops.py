# -*- coding: utf-8 -*-
"""Operational summary tests for P2.5."""

from __future__ import annotations

from datetime import datetime, timezone

from products.tech_blog_monitor.archive_store import ArchiveStore
from products.tech_blog_monitor.db.engine import build_sqlite_url
from products.tech_blog_monitor.db.schema_manager import bootstrap_schema
from products.tech_blog_monitor.fetcher import Article
from products.tech_blog_monitor.ops import build_operational_summary
from products.tech_blog_monitor.repository_provider import open_repository_bundle


def _article(url: str = "https://example.com/a") -> Article:
    published = datetime(2026, 4, 10, tzinfo=timezone.utc)
    article = Article(
        title="Article A",
        url=url,
        source_name="Source A",
        category="行业风向标",
        source_id=f"Source A::{url}",
        rss_summary="raw summary",
        published=published,
        published_ts=int(published.timestamp()),
        fetched_at=int(published.timestamp()),
    )
    article.one_line_summary = "summary"
    article.why_it_matters = "matters"
    article.topic = "智能体"
    article.tags = ["agent"]
    article.enrichment_status = "enriched"
    return article


def _build_store(tmp_path) -> str:
    db_path = tmp_path / "assets.db"
    article = _article()
    with ArchiveStore(str(db_path)) as store:
        store.record_run(
            generated_at=1744675200,
            generated_at_iso="2025-04-15T00:00:00+00:00",
            output_path="/tmp/report.md",
            view="by_category",
            incremental_mode="split",
            all_articles=[article],
            report_articles=[article],
            new_urls={article.url},
        )
    bootstrap_schema(build_sqlite_url(str(db_path)))
    return str(db_path)


def _insert_task(bundle, *, task_id: str, task_status: str, run_summary: dict, started_at: int) -> None:
    bundle.task_repository.create_task(
        task_id=task_id,
        task_type="manual_run",
        task_status=task_status,
        trigger_source="cli",
        requested_by="cli",
        idempotency_key=f"idem:{task_id}",
        scope="report:/tmp/report.md",
        artifact_uri="/tmp/report.md",
        input_payload={"output_path": "/tmp/report.md"},
        result_payload={"exit_code": 0 if task_status == "succeeded" else 1, "run_summary": run_summary},
        max_retries=0,
        retry_count=0,
        started_at=started_at,
        finished_at=started_at + 30,
        error_code="" if task_status == "succeeded" else "NonZeroExitCode",
        error_message="" if task_status == "succeeded" else "monitor.run returned exit code 1",
    )


def test_build_operational_summary_aggregates_kpis(tmp_path):
    db_path = _build_store(tmp_path)
    success_summary = {
        "duration_ms": 1200,
        "feed_stats": {"success": 4, "failure": 1, "disabled": 0},
        "content_status_counts": {"fetched": 8, "low_quality": 2, "fetch_error": 1},
        "enrichment_status_counts": {"enriched": 8, "failed": 2},
        "delivery_status_counts": {"delivered": 3, "failed": 1},
        "status": "success",
    }
    failed_summary = {
        "duration_ms": 1800,
        "feed_stats": {"success": 3, "failure": 2, "disabled": 0},
        "content_status_counts": {"fetched": 4, "low_quality": 1, "http_error": 1},
        "enrichment_status_counts": {"enriched": 4, "failed": 1},
        "delivery_status_counts": {"delivered": 1, "failed": 1},
        "status": "failed",
    }
    with open_repository_bundle(asset_db_path=db_path) as bundle:
        _insert_task(bundle, task_id="task_1", task_status="succeeded", run_summary=success_summary, started_at=100)
        _insert_task(bundle, task_id="task_2", task_status="failed", run_summary=failed_summary, started_at=200)

    summary = build_operational_summary(db_path, limit=10)
    kpis = {item.name: item for item in summary.kpis}

    assert summary.window_size == 2
    assert summary.task_status_counts == {"failed": 1, "succeeded": 1}
    assert kpis["run_success_rate"].value == 0.5
    assert kpis["feed_availability"].value == 0.7
    assert kpis["content_extraction_pass_rate"].value == 0.7059
    assert kpis["low_quality_ratio"].value == 0.1765
    assert kpis["enrichment_failure_rate"].value == 0.2
    assert kpis["delivery_success_rate"].value == 0.6667
    assert kpis["mean_run_duration_ms"].value == 1500.0
    assert summary.recent_failures[0].task_id == "task_2"


def test_build_operational_summary_handles_empty_window(tmp_path):
    db_path = _build_store(tmp_path)

    summary = build_operational_summary(db_path, limit=10)
    kpis = {item.name: item for item in summary.kpis}

    assert summary.window_size == 0
    assert summary.task_status_counts == {}
    assert summary.task_type_counts == {}
    assert summary.recent_failures == []
    assert summary.latest_task_id == ""
    assert summary.latest_run_task_id == ""
    assert kpis["run_success_rate"].value is None
    assert kpis["feed_availability"].value is None
    assert kpis["content_extraction_pass_rate"].value is None
    assert kpis["low_quality_ratio"].value is None
    assert kpis["enrichment_failure_rate"].value is None
    assert kpis["delivery_success_rate"].value is None
    assert kpis["mean_run_duration_ms"].value is None


def test_build_operational_summary_ignores_noise_and_limits_recent_failures(tmp_path):
    db_path = _build_store(tmp_path)
    noisy_summary = {
        "duration_ms": True,
        "feed_stats": {"success": "3", "failure": None, "disabled": 0},
        "content_status_counts": {"fetched": "8", "low_quality": False, "http_error": "bad"},
        "enrichment_status_counts": {"enriched": "oops", "failed": True},
        "delivery_status_counts": {"delivered": "1", "failed": []},
        "status": "failed",
    }
    with open_repository_bundle(asset_db_path=db_path) as bundle:
        for index in range(6):
            bundle.task_repository.create_task(
                task_id=f"task_failure_{index}",
                task_type="manual_run",
                task_status="failed",
                trigger_source="cli",
                requested_by="cli",
                idempotency_key=f"idem:failure:{index}",
                scope="report:/tmp/report.md",
                artifact_uri="/tmp/report.md",
                input_payload={"output_path": "/tmp/report.md"},
                result_payload={"exit_code": 1, "run_summary": noisy_summary},
                max_retries=0,
                retry_count=0,
                started_at=100 + index,
                finished_at=130 + index,
                error_code="NonZeroExitCode",
                error_message=f"failed-{index}",
            )

    summary = build_operational_summary(db_path, limit=10)
    kpis = {item.name: item for item in summary.kpis}

    assert summary.window_size == 6
    assert len(summary.recent_failures) == 5
    assert summary.recent_failures[0].task_id == "task_failure_5"
    assert summary.recent_failures[-1].task_id == "task_failure_1"
    assert kpis["feed_availability"].value is None
    assert kpis["content_extraction_pass_rate"].value is None
    assert kpis["low_quality_ratio"].value is None
    assert kpis["delivery_success_rate"].value is None
    assert kpis["mean_run_duration_ms"].value == 1.0
