# -*- coding: utf-8 -*-
"""Tech Blog Monitor Phase 7 delivery tests."""

from datetime import datetime, timezone

from products.tech_blog_monitor.archive_store import ArchiveStore
from products.tech_blog_monitor.delivery import (
    DeliveryRequest,
    build_role_digest,
    maybe_dispatch_deliveries,
)
from products.tech_blog_monitor.fetcher import Article
from products.tech_blog_monitor.insights import InsightReport


def _article(title: str, url: str, topic: str = "智能体") -> Article:
    published = datetime(2025, 4, 15, tzinfo=timezone.utc)
    article = Article(
        title=title,
        url=url,
        source_name="OpenAI News",
        category="AI Agent/工程实践",
        source_id=f"OpenAI News::{url}",
        rss_summary=f"{title} rss",
        published=published,
        published_ts=int(published.timestamp()),
        fetched_at=int(published.timestamp()),
        clean_text=f"{title} clean text",
        content_status="fetched",
        content_source="html_article",
    )
    article.one_line_summary = f"{title} summary"
    article.topic = topic
    article.key_points = [f"{title} point"]
    article.recommended_for = ["工程师"]
    article.tags = [topic]
    article.enrichment_status = "enriched"
    return article


def _build_store(tmp_path):
    db_path = tmp_path / "assets.db"
    article = _article("Agent Memory Systems", "https://example.com/a")
    with ArchiveStore(str(db_path)) as store:
        run_id = store.record_run(
            generated_at=1744675200,
            generated_at_iso="2025-04-15T00:00:00+00:00",
            output_path="/tmp/report.md",
            view="by_category",
            incremental_mode="split",
            all_articles=[article],
            report_articles=[article],
            new_urls={article.url},
        )
    return str(db_path), run_id, [article]


def _insight_report() -> InsightReport:
    return InsightReport(
        status="ok",
        summary="智能体主题持续上升。",
        topic_clusters=[],
        source_comparisons=[],
        timeline=[],
        hot_signals=[],
    )


def test_build_role_digest_uses_role_template():
    article = _article("Agent Memory Systems", "https://example.com/a")
    payload = build_role_digest(
        role="executive",
        report_markdown="# report",
        articles=[article],
        insight_report=_insight_report(),
        generated_at=1744675200,
        cadence="daily",
    )
    assert payload["role"] == "executive"
    assert "管理层摘要" in payload["text"]


def test_delivery_is_idempotent_for_same_run_and_role(tmp_path):
    db_path, run_id, articles = _build_store(tmp_path)
    sent_payloads = []

    def sender(url, payload):
        sent_payloads.append(payload)
        return 200, "ok"

    request = DeliveryRequest(
        run_id=run_id,
        generated_at=1744675200,
        cadence="daily",
        webhook_url="https://example.com/webhook",
        roles=["executive"],
    )
    maybe_dispatch_deliveries(
        db_path=db_path,
        request=request,
        report_markdown="# report",
        articles=articles,
        insight_report=_insight_report(),
        sender=sender,
        now_ts=1744675200,
    )
    maybe_dispatch_deliveries(
        db_path=db_path,
        request=request,
        report_markdown="# report",
        articles=articles,
        insight_report=_insight_report(),
        sender=sender,
        now_ts=1744675201,
    )

    with ArchiveStore(db_path) as store:
        deliveries = store.list_deliveries(run_id=run_id)
        assert len(deliveries) == 1
        assert deliveries[0]["status"] == "delivered"
    assert len(sent_payloads) == 1


def test_delivery_retries_and_then_fails(tmp_path):
    db_path, run_id, articles = _build_store(tmp_path)

    def sender(url, payload):
        return 500, "server error"

    request = DeliveryRequest(
        run_id=run_id,
        generated_at=1744675200,
        cadence="daily",
        webhook_url="https://example.com/webhook",
        roles=["engineer"],
        max_retries=2,
    )
    maybe_dispatch_deliveries(
        db_path=db_path,
        request=request,
        report_markdown="# report",
        articles=articles,
        insight_report=_insight_report(),
        sender=sender,
        now_ts=1744675200,
    )
    maybe_dispatch_deliveries(
        db_path=db_path,
        request=request,
        report_markdown="# report",
        articles=articles,
        insight_report=_insight_report(),
        sender=sender,
        now_ts=1744675260,
    )

    with ArchiveStore(db_path) as store:
        deliveries = store.list_deliveries(run_id=run_id)
        assert deliveries[0]["status"] == "failed"
        assert deliveries[0]["attempt_count"] == 2


def test_delivery_rate_limit_marks_extra_items(tmp_path):
    db_path, run_id, articles = _build_store(tmp_path)

    def sender(url, payload):
        return 200, "ok"

    request = DeliveryRequest(
        run_id=run_id,
        generated_at=1744675200,
        cadence="daily",
        webhook_url="https://example.com/webhook",
        roles=["executive", "engineer"],
        rate_limit_per_minute=1,
    )
    maybe_dispatch_deliveries(
        db_path=db_path,
        request=request,
        report_markdown="# report",
        articles=articles,
        insight_report=_insight_report(),
        sender=sender,
        now_ts=1744675200,
    )

    with ArchiveStore(db_path) as store:
        deliveries = store.list_deliveries(run_id=run_id)
        statuses = {item["role"]: item["status"] for item in deliveries}
        assert "delivered" in statuses.values()
        assert "rate_limited" in statuses.values()


def test_delivery_sender_exception_is_downgraded_to_retryable_failure(tmp_path):
    db_path, run_id, articles = _build_store(tmp_path)

    def sender(url, payload):
        raise RuntimeError("webhook down")

    request = DeliveryRequest(
        run_id=run_id,
        generated_at=1744675200,
        cadence="daily",
        webhook_url="https://example.com/webhook",
        roles=["executive"],
        max_retries=2,
    )
    maybe_dispatch_deliveries(
        db_path=db_path,
        request=request,
        report_markdown="# report",
        articles=articles,
        insight_report=_insight_report(),
        sender=sender,
        now_ts=1744675200,
    )

    with ArchiveStore(db_path) as store:
        deliveries = store.list_deliveries(run_id=run_id)
        assert deliveries[0]["status"] == "pending"
        assert deliveries[0]["attempt_count"] == 1
        assert "webhook down" in deliveries[0]["last_error"]

    maybe_dispatch_deliveries(
        db_path=db_path,
        request=request,
        report_markdown="# report",
        articles=articles,
        insight_report=_insight_report(),
        sender=sender,
        now_ts=1744675260,
    )

    with ArchiveStore(db_path) as store:
        deliveries = store.list_deliveries(run_id=run_id)
        assert deliveries[0]["status"] == "failed"
        assert deliveries[0]["attempt_count"] == 2
