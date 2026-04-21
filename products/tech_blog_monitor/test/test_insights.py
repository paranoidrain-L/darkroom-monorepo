# -*- coding: utf-8 -*-
"""Tech Blog Monitor Phase 6 insights tests."""

from datetime import datetime, timezone

import pytest

from products.tech_blog_monitor.archive_store import ArchiveStore
from products.tech_blog_monitor.fetcher import Article
from products.tech_blog_monitor.insights import (
    InsightQuery,
    analyze_insights,
    format_insight_report,
)
from products.tech_blog_monitor.insights_cli import main as insights_cli_main
from products.tech_blog_monitor.observability.metrics import (
    get_default_metrics_registry,
    reset_default_metrics_registry,
)


def _article(
    title: str,
    url: str,
    source_name: str,
    category: str,
    published_ts: int,
    topic: str,
):
    published = datetime.fromtimestamp(published_ts, tz=timezone.utc)
    article = Article(
        title=title,
        url=url,
        source_name=source_name,
        category=category,
        source_id=f"{source_name}::{url}",
        rss_summary=f"{title} rss summary",
        published=published,
        published_ts=published_ts,
        fetched_at=published_ts,
        clean_text=f"{title} clean text about {topic}",
        content_status="fetched",
        content_source="html_article",
    )
    article.one_line_summary = f"{title} summary"
    article.why_it_matters = f"{title} matters"
    article.topic = topic
    article.tags = [topic]
    article.key_points = [f"{title} point"]
    article.recommended_for = ["工程师"]
    article.enrichment_status = "enriched"
    return article


def _build_trend_store(tmp_path):
    db_path = tmp_path / "assets.db"
    anchor_ts = int(datetime(2025, 4, 15, tzinfo=timezone.utc).timestamp())
    recent = [
        _article(
            title=f"Agent Update {index}",
            url=f"https://example.com/agent-{index}",
            source_name="OpenAI News" if index % 2 == 0 else "Anthropic",
            category="AI Agent/工程实践",
            published_ts=anchor_ts - index * 86400,
            topic="智能体",
        )
        for index in range(4)
    ]
    recent += [
        _article(
            title="Infra Update 0",
            url="https://example.com/infra-0",
            source_name="NVIDIA Technical Blog",
            category="深度技术",
            published_ts=anchor_ts - 2 * 86400,
            topic="基础设施",
        )
    ]
    previous = [
        _article(
            title=f"Agent Older {index}",
            url=f"https://example.com/agent-old-{index}",
            source_name="OpenAI News",
            category="AI Agent/工程实践",
            published_ts=anchor_ts - (8 + index) * 86400,
            topic="智能体",
        )
        for index in range(1)
    ]
    previous += [
        _article(
            title=f"Safety Older {index}",
            url=f"https://example.com/safety-old-{index}",
            source_name="DeepMind",
            category="行业风向标",
            published_ts=anchor_ts - (8 + index) * 86400,
            topic="安全评测",
        )
        for index in range(3)
    ]

    with ArchiveStore(str(db_path)) as store:
        store.record_run(
            generated_at=anchor_ts,
            generated_at_iso="2025-04-15T00:00:00+00:00",
            output_path="/tmp/report.md",
            view="by_category",
            incremental_mode="split",
            all_articles=recent + previous,
            report_articles=recent + previous,
            new_urls={article.url for article in recent},
        )
    return str(db_path), anchor_ts


def test_insights_detects_rising_and_falling_topics(tmp_path):
    db_path, anchor_ts = _build_trend_store(tmp_path)
    report = analyze_insights(
        db_path,
        InsightQuery(days=7, top_k=5, anchor_ts=anchor_ts + 1),
    )
    assert report.status == "ok"
    cluster_by_topic = {cluster.topic: cluster for cluster in report.topic_clusters}
    assert cluster_by_topic["智能体"].trend_label == "rising"
    assert cluster_by_topic["智能体"].delta == 3
    assert "智能体" in report.summary


def test_insights_source_comparison_reflects_different_focus(tmp_path):
    db_path, anchor_ts = _build_trend_store(tmp_path)
    report = analyze_insights(
        db_path,
        InsightQuery(days=7, top_k=5, anchor_ts=anchor_ts + 1),
    )
    source_names = {item.source_name for item in report.source_comparisons}
    assert "OpenAI News" in source_names
    assert "Anthropic" in source_names
    openai = next(item for item in report.source_comparisons if item.source_name == "OpenAI News")
    assert "智能体" in openai.dominant_topics


def test_insights_timeline_is_stable_and_ordered(tmp_path):
    db_path, anchor_ts = _build_trend_store(tmp_path)
    report = analyze_insights(
        db_path,
        InsightQuery(days=7, top_k=5, anchor_ts=anchor_ts + 1),
    )
    assert len(report.timeline) == 7
    assert report.timeline[0].date < report.timeline[-1].date
    assert any(point.top_topic == "智能体" for point in report.timeline)


def test_insights_degrades_when_signal_is_low(tmp_path):
    db_path = tmp_path / "assets.db"
    anchor_ts = int(datetime(2025, 4, 15, tzinfo=timezone.utc).timestamp())
    articles = [
        _article(
            title="Single Agent Article",
            url="https://example.com/single",
            source_name="OpenAI News",
            category="AI Agent/工程实践",
            published_ts=anchor_ts - 86400,
            topic="智能体",
        )
    ]
    with ArchiveStore(str(db_path)) as store:
        store.record_run(
            generated_at=anchor_ts,
            generated_at_iso="2025-04-15T00:00:00+00:00",
            output_path="/tmp/report.md",
            view="by_category",
            incremental_mode="split",
            all_articles=articles,
            report_articles=articles,
            new_urls={articles[0].url},
        )

    report = analyze_insights(
        str(db_path),
        InsightQuery(days=7, top_k=5, anchor_ts=anchor_ts + 1),
    )
    assert report.status == "insufficient_data"
    assert "事实汇总" in report.summary


def test_format_insight_report_contains_sections(tmp_path):
    db_path, anchor_ts = _build_trend_store(tmp_path)
    report = analyze_insights(
        db_path,
        InsightQuery(days=7, top_k=5, anchor_ts=anchor_ts + 1),
    )
    text = format_insight_report(report)
    assert "## 主题簇" in text
    assert "## 多来源对比" in text
    assert "## 时间线" in text
    assert "## 热点信号" in text


def test_insights_cli_missing_db_exits_nonzero(monkeypatch, tmp_path, capsys):
    missing = tmp_path / "missing.db"
    monkeypatch.setattr(
        "sys.argv",
        ["insights_cli.py", "--db", str(missing)],
    )

    with pytest.raises(SystemExit) as exc:
        insights_cli_main()

    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "资产库不存在" in captured.err


def test_insights_records_latency_metric(tmp_path):
    reset_default_metrics_registry()
    db_path, anchor_ts = _build_trend_store(tmp_path)

    report = analyze_insights(
        db_path,
        InsightQuery(days=7, top_k=5, anchor_ts=anchor_ts + 1),
    )

    assert report.status == "ok"
    snapshot = get_default_metrics_registry().snapshot()
    assert snapshot["histograms"]["insights_latency_ms"]["count"] == 1
