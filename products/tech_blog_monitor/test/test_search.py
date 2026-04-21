# -*- coding: utf-8 -*-
"""Tech Blog Monitor search 单元测试。"""

from datetime import datetime, timezone

import pytest

from products.tech_blog_monitor.archive_store import ArchiveStore
from products.tech_blog_monitor.db.engine import build_sqlite_url
from products.tech_blog_monitor.fetcher import Article
from products.tech_blog_monitor.observability.metrics import (
    get_default_metrics_registry,
    reset_default_metrics_registry,
)
from products.tech_blog_monitor.search import SearchQuery, format_search_results, search_articles


def _article(
    title: str,
    url: str,
    source_name: str,
    category: str,
    published_ts: int,
    rss_summary: str = "",
    clean_text: str = "",
    topic: str = "",
    tags: list[str] | None = None,
):
    published = datetime.fromtimestamp(published_ts, tz=timezone.utc)
    article = Article(
        title=title,
        url=url,
        source_name=source_name,
        category=category,
        source_id=f"{source_name}::{url}",
        rss_summary=rss_summary,
        published=published,
        published_ts=published_ts,
        fetched_at=published_ts,
        clean_text=clean_text,
        content_status="fetched" if clean_text else "not_fetched",
        content_source="html_article" if clean_text else "",
    )
    article.one_line_summary = f"{title} summary"
    article.why_it_matters = f"{title} matters"
    article.topic = topic
    article.tags = list(tags or [])
    article.key_points = [f"{title} point"]
    article.recommended_for = ["工程师"]
    article.enrichment_status = "enriched"
    article.relevance_score = 5.0 if "agent" in " ".join(article.tags).lower() else 1.5
    article.relevance_level = "medium" if article.relevance_score >= 3 else "low"
    article.relevance_reasons = [f"topic:{topic} 命中"]
    article.matched_signals = [{"signal_name": topic or "unknown", "signal_kind": "topic"}]
    article.topic_match_score = article.relevance_score - 0.6
    article.source_priority_score = 0.6
    return article


def _build_store(tmp_path):
    db_path = tmp_path / "assets.db"
    articles = [
        _article(
            title="Agent Systems at Scale",
            url="https://example.com/agent",
            source_name="OpenAI News",
            category="AI Agent/工程实践",
            published_ts=1744588800,  # 2025-04-14 UTC
            rss_summary="Agent systems summary",
            clean_text="This article discusses agent orchestration and routing.",
            topic="智能体",
            tags=["agent", "orchestration"],
        ),
        _article(
            title="Inference Infrastructure Deep Dive",
            url="https://example.com/infra",
            source_name="NVIDIA Technical Blog",
            category="深度技术",
            published_ts=1741996800,  # 2025-03-15 UTC
            rss_summary="Inference infrastructure summary",
            clean_text="Inference serving, batching, and GPU scheduling.",
            topic="基础设施",
            tags=["infra", "inference"],
        ),
        _article(
            title="Multi-modal Evaluation Update",
            url="https://example.com/multimodal",
            source_name="DeepMind",
            category="行业风向标",
            published_ts=1739577600,  # 2025-02-15 UTC
            rss_summary="Evaluation summary",
            clean_text="Benchmarking and multimodal evaluation signals.",
            topic="评测",
            tags=["evaluation", "multimodal"],
        ),
    ]

    with ArchiveStore(str(db_path)) as store:
        store.record_run(
            generated_at=1744675200,
            generated_at_iso="2025-04-15T00:00:00+00:00",
            output_path="/tmp/report.md",
            view="by_category",
            incremental_mode="split",
            all_articles=articles,
            report_articles=articles,
            new_urls={articles[0].url},
        )
    return str(db_path)


def test_search_by_keyword_returns_ranked_results(tmp_path):
    db_path = _build_store(tmp_path)
    results = search_articles(db_path, SearchQuery(query="agent"))
    assert len(results) == 1
    assert results[0]["title"] == "Agent Systems at Scale"
    assert results[0]["relevance_level"] == "medium"


def test_search_by_source_filter(tmp_path):
    db_path = _build_store(tmp_path)
    results = search_articles(db_path, SearchQuery(source_name="NVIDIA Technical Blog"))
    assert len(results) == 1
    assert results[0]["source_name"] == "NVIDIA Technical Blog"


def test_search_by_topic_filter(tmp_path):
    db_path = _build_store(tmp_path)
    results = search_articles(db_path, SearchQuery(topic="基础设施"))
    assert len(results) == 1
    assert results[0]["topic"] == "基础设施"


def test_search_by_tag_filter(tmp_path):
    db_path = _build_store(tmp_path)
    results = search_articles(db_path, SearchQuery(tag="multimodal"))
    assert len(results) == 1
    assert results[0]["title"] == "Multi-modal Evaluation Update"


def test_search_by_days_filter(tmp_path, monkeypatch):
    db_path = _build_store(tmp_path)

    class _FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2025, 4, 15, tzinfo=timezone.utc)

    monkeypatch.setattr("products.tech_blog_monitor.search.datetime", _FrozenDatetime)
    results = search_articles(db_path, SearchQuery(days=30))
    assert [item["title"] for item in results] == ["Agent Systems at Scale"]


def test_search_combined_filters(tmp_path):
    db_path = _build_store(tmp_path)
    results = search_articles(
        db_path,
        SearchQuery(query="inference", source_name="NVIDIA Technical Blog", topic="基础设施"),
    )
    assert len(results) == 1
    assert results[0]["title"] == "Inference Infrastructure Deep Dive"


def test_search_empty_results(tmp_path):
    db_path = _build_store(tmp_path)
    results = search_articles(db_path, SearchQuery(query="nonexistent"))
    assert results == []
    assert format_search_results(results) == "未找到匹配文章。"


def test_format_search_results_contains_url_and_tags(tmp_path):
    db_path = _build_store(tmp_path)
    results = search_articles(db_path, SearchQuery(query="agent"))
    text = format_search_results(results)
    assert "https://example.com/agent" in text
    assert "tags: agent, orchestration" in text


def test_search_missing_db_raises_and_does_not_create_file(tmp_path):
    db_path = tmp_path / "missing.db"
    with pytest.raises(FileNotFoundError):
        search_articles(str(db_path), SearchQuery(query="agent"))
    assert not db_path.exists()


def test_search_uses_database_url_when_provided(tmp_path):
    db_path = _build_store(tmp_path)
    results = search_articles(
        str(tmp_path / "missing.db"),
        SearchQuery(query="agent"),
        database_url=build_sqlite_url(db_path),
    )
    assert results[0]["title"] == "Agent Systems at Scale"


def test_search_records_latency_metric(tmp_path):
    reset_default_metrics_registry()
    db_path = _build_store(tmp_path)

    results = search_articles(db_path, SearchQuery(query="agent"))

    assert results[0]["title"] == "Agent Systems at Scale"
    snapshot = get_default_metrics_registry().snapshot()
    assert snapshot["histograms"]["search_latency_ms"]["count"] == 1
