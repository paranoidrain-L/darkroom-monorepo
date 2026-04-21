# -*- coding: utf-8 -*-
"""Tech Blog Monitor fetcher 单元测试。"""

import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from products.tech_blog_monitor.config import FeedSource, TechBlogMonitorConfig
from products.tech_blog_monitor.fetcher import (
    Article,
    FeedHealth,
    _passes_keyword_filter,
    fetch_all,
    fetch_feed,
    fetch_source,
)

_UTC = timezone.utc
_NOW = datetime(2026, 4, 13, 12, 0, 0, tzinfo=_UTC)


def _article(title="T", url="https://example.com/1", published=None, rss_summary="", category="A", source="S"):
    return Article(
        title=title, url=url, published=published, rss_summary=rss_summary,
        source_name=source, category=category,
        source_id=f"{source}::{url}",
        published_ts=int(published.timestamp()) if published else None,
        fetched_at=0,
    )


def _feed(name="F", url="https://f.com/rss", category="C", enabled=True, verify_ssl=True, timeout=15):
    return FeedSource(name=name, url=url, category=category, enabled=enabled,
                      verify_ssl=verify_ssl, timeout=timeout)


def _mock_response(content=b"<rss/>"):
    resp = SimpleNamespace(content=content)
    resp.raise_for_status = lambda: None
    return resp


# ── fetch_feed ────────────────────────────────────────────────────────────────

def test_fetch_feed_parses_articles(monkeypatch):
    source = _feed("Test Feed", "https://example.com/rss.xml", "测试分类")
    entry = {
        "title": "  Test Title  ",
        "link": " https://example.com/post ",
        "summary": "<p>Hello <b>World</b></p>",
        "published_parsed": time.struct_time((2026, 4, 10, 11, 30, 0, 4, 100, -1)),
    }
    monkeypatch.setattr("products.tech_blog_monitor.fetcher.requests.get",
                        lambda *a, **kw: _mock_response())
    monkeypatch.setattr("products.tech_blog_monitor.fetcher.feedparser.parse",
                        lambda content: SimpleNamespace(entries=[entry]))

    articles, health = fetch_feed(source, max_articles=1)

    assert len(articles) == 1
    assert articles[0].title == "Test Title"
    assert articles[0].url == "https://example.com/post"
    assert articles[0].rss_summary == "Hello World"
    assert articles[0].published is not None
    assert articles[0].published.hour == 19
    assert health.success is True
    assert health.article_count == 1
    assert health.retries == 0


def test_fetch_feed_disabled_source():
    source = _feed(enabled=False)
    articles, health = fetch_feed(source, max_articles=5)
    assert articles == []
    assert health.success is False
    assert health.error == "disabled"


def test_fetch_feed_retries_on_failure(monkeypatch):
    """失败时重试，最终仍失败返回空列表和健康状态。"""
    call_count = {"n": 0}

    def failing_get(*a, **kw):
        call_count["n"] += 1
        raise Exception("connection error")

    monkeypatch.setattr("products.tech_blog_monitor.fetcher.requests.get", failing_get)
    monkeypatch.setattr("products.tech_blog_monitor.fetcher.time.sleep", lambda _: None)

    source = _feed()
    articles, health = fetch_feed(source, max_articles=5)

    assert articles == []
    assert health.success is False
    assert health.retries == 3
    assert call_count["n"] == 3


def test_fetch_feed_succeeds_on_second_attempt(monkeypatch):
    """第一次失败，第二次成功。"""
    attempts = {"n": 0}

    def flaky_get(*a, **kw):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise Exception("timeout")
        return _mock_response()

    monkeypatch.setattr("products.tech_blog_monitor.fetcher.requests.get", flaky_get)
    monkeypatch.setattr("products.tech_blog_monitor.fetcher.feedparser.parse",
                        lambda content: SimpleNamespace(entries=[]))
    monkeypatch.setattr("products.tech_blog_monitor.fetcher.time.sleep", lambda _: None)

    source = _feed()
    articles, health = fetch_feed(source, max_articles=5)

    assert health.success is True
    assert health.retries == 1


def test_fetch_feed_uses_source_verify_ssl(monkeypatch):
    """verify_ssl=False 时传递给 requests.get。"""
    captured = {}

    def mock_get(url, timeout, headers, verify):
        captured["verify"] = verify
        return _mock_response()

    monkeypatch.setattr("products.tech_blog_monitor.fetcher.requests.get", mock_get)
    monkeypatch.setattr("products.tech_blog_monitor.fetcher.feedparser.parse",
                        lambda content: SimpleNamespace(entries=[]))

    source = _feed(verify_ssl=False)
    fetch_feed(source, max_articles=5)
    assert captured["verify"] is False


def test_fetch_feed_uses_source_timeout(monkeypatch):
    """timeout 使用 source.timeout 而非全局常量。"""
    captured = {}

    def mock_get(url, timeout, headers, verify):
        captured["timeout"] = timeout
        return _mock_response()

    monkeypatch.setattr("products.tech_blog_monitor.fetcher.requests.get", mock_get)
    monkeypatch.setattr("products.tech_blog_monitor.fetcher.feedparser.parse",
                        lambda content: SimpleNamespace(entries=[]))

    source = _feed(timeout=30)
    fetch_feed(source, max_articles=5)
    assert captured["timeout"] == 30


# ── fetch_all ─────────────────────────────────────────────────────────────────

def _make_config(feeds, **kwargs):
    defaults = dict(max_age_days=0, max_articles_per_source=0, max_total_articles=0,
                    fetch_workers=2)
    defaults.update(kwargs)
    return TechBlogMonitorConfig(feeds=feeds, **defaults)


def _patch_fetch_source(monkeypatch, results: dict):
    """results: {source_name: ([Article, ...], FeedHealth)}"""
    def mock_fetch(source, max_articles, session=None, adapters=None):
        return results.get(source.name, ([], FeedHealth(name=source.name, url=source.url,
                                                         success=False, error="not mocked", source_type=source.source_type)))
    monkeypatch.setattr("products.tech_blog_monitor.fetcher.fetch_source", mock_fetch)


def test_fetch_all_returns_articles_and_health(monkeypatch):
    feeds = [_feed("A", "https://a.com/rss", "C")]
    a = _article(title="A1", url="https://a.com/1", published=_NOW)
    _patch_fetch_source(monkeypatch, {"A": ([a], FeedHealth("A", "https://a.com/rss", True, 1))})

    articles, health_list = fetch_all(_make_config(feeds))
    assert len(articles) == 1
    assert len(health_list) == 1
    assert health_list[0].success is True


def test_fetch_all_sorts_by_published(monkeypatch):
    feeds = [_feed("A"), _feed("B", "https://b.com/rss")]
    older = _article(title="Older", url="https://a.com/1", published=_NOW - timedelta(days=2))
    newer = _article(title="Newer", url="https://b.com/1", published=_NOW - timedelta(days=1))
    _patch_fetch_source(monkeypatch, {
        "A": ([older], FeedHealth("A", "", True, 1)),
        "B": ([newer], FeedHealth("B", "", True, 1)),
    })

    articles, _ = fetch_all(_make_config(feeds))
    assert [a.title for a in articles] == ["Newer", "Older"]


def test_fetch_all_age_filter(monkeypatch):
    feeds = [_feed("X")]
    fresh = _article(title="Fresh", url="https://x.com/1", published=_NOW - timedelta(days=3))
    stale = _article(title="Stale", url="https://x.com/2", published=_NOW - timedelta(days=10))
    _patch_fetch_source(monkeypatch, {"X": ([fresh, stale], FeedHealth("X", "", True, 2))})

    with patch("products.tech_blog_monitor.fetcher.datetime") as mock_dt:
        mock_dt.now.return_value = _NOW
        mock_dt.min = datetime.min
        articles, _ = fetch_all(_make_config(feeds, max_age_days=7))

    titles = [a.title for a in articles]
    assert "Fresh" in titles
    assert "Stale" not in titles


def test_fetch_all_url_dedup(monkeypatch):
    feeds = [_feed("A"), _feed("B", "https://b.com/rss")]
    a1 = _article(title="A1", url="https://dup.com/1", published=_NOW)
    a2 = _article(title="A2", url="https://dup.com/1", published=_NOW)  # 同 url
    _patch_fetch_source(monkeypatch, {
        "A": ([a1], FeedHealth("A", "", True, 1)),
        "B": ([a2], FeedHealth("B", "", True, 1)),
    })

    articles, _ = fetch_all(_make_config(feeds))
    assert len(articles) == 1


def test_fetch_all_per_source_limit(monkeypatch):
    feeds = [_feed("S")]
    arts = [_article(title=f"T{i}", url=f"https://s.com/{i}", published=_NOW) for i in range(5)]
    _patch_fetch_source(monkeypatch, {"S": (arts, FeedHealth("S", "", True, 5))})

    articles, _ = fetch_all(_make_config(feeds, max_articles_per_source=2))
    assert len(articles) == 2


def test_fetch_all_total_limit(monkeypatch):
    feeds = [_feed("T")]
    arts = [_article(title=f"T{i}", url=f"https://t.com/{i}",
                     published=_NOW - timedelta(hours=i)) for i in range(10)]
    _patch_fetch_source(monkeypatch, {"T": (arts, FeedHealth("T", "", True, 10))})

    articles, _ = fetch_all(_make_config(feeds, max_total_articles=3))
    assert len(articles) == 3


def test_fetch_all_disabled_feed_in_health(monkeypatch):
    """disabled feed 出现在 health_list 中，但不贡献文章。"""
    feeds = [_feed("Enabled"), _feed("Disabled", enabled=False)]
    a = _article(url="https://e.com/1", published=_NOW)
    _patch_fetch_source(monkeypatch, {"Enabled": ([a], FeedHealth("Enabled", "", True, 1))})

    articles, health_list = fetch_all(_make_config(feeds))
    assert len(articles) == 1
    disabled_health = next(h for h in health_list if h.name == "Disabled")
    assert disabled_health.success is False
    assert disabled_health.error == "disabled"


def test_fetch_all_failed_feed_does_not_block(monkeypatch):
    """一个源失败不影响其他源的结果。"""
    feeds = [_feed("Good"), _feed("Bad", "https://bad.com/rss")]
    a = _article(url="https://good.com/1", published=_NOW)
    _patch_fetch_source(monkeypatch, {
        "Good": ([a], FeedHealth("Good", "", True, 1)),
        "Bad": ([], FeedHealth("Bad", "", False, error="404")),
    })

    articles, health_list = fetch_all(_make_config(feeds))
    assert len(articles) == 1
    bad_health = next(h for h in health_list if h.name == "Bad")
    assert bad_health.success is False


def test_fetch_source_uses_fake_adapter_contract():
    class FakeAdapter:
        @property
        def source_type(self) -> str:
            return "fake"

        def fetch(self, source, *, max_articles, session=None):
            article = _article(
                title="Fake Source Article",
                url="https://fake.local/article",
                published=_NOW,
                category=source.category,
                source=source.name,
            )
            return [article], FeedHealth(
                name=source.name,
                url=source.url,
                success=True,
                article_count=1,
                source_type=source.source_type,
            )

    source = _feed(name="Fake Source", url="memory://fake", category="测试", timeout=1)
    source.source_type = "fake"

    articles, health = fetch_source(
        source,
        max_articles=5,
        adapters={"fake": FakeAdapter()},
    )

    assert len(articles) == 1
    assert articles[0].source_name == "Fake Source"
    assert health.source_type == "fake"


def test_fetch_all_runs_through_adapter_layer_for_non_rss_source():
    class FakeAdapter:
        @property
        def source_type(self) -> str:
            return "fake"

        def fetch(self, source, *, max_articles, session=None):
            article = _article(
                title="Adapter Article",
                url="https://fake.local/adapter",
                published=_NOW,
                category=source.category,
                source=source.name,
            )
            return [article], FeedHealth(
                name=source.name,
                url=source.url,
                success=True,
                article_count=1,
                source_type=source.source_type,
            )

    source = _feed(name="InMemory", url="memory://adapter", category="测试")
    source.source_type = "fake"
    config = _make_config([source])

    articles, health_list = fetch_all(config, adapters={"fake": FakeAdapter()})

    assert [article.title for article in articles] == ["Adapter Article"]
    assert len(health_list) == 1
    assert health_list[0].source_type == "fake"


# ── keyword filter ────────────────────────────────────────────────────────────

class TestKeywordFilter:
    def test_no_rules_passes(self):
        assert _passes_keyword_filter(_article(), {}) is True

    def test_category_rule_match(self):
        a = _article(title="LiDAR detection paper", category="自动驾驶/3D感知")
        assert _passes_keyword_filter(a, {"自动驾驶/3D感知": ["lidar", "detection"]}) is True

    def test_category_rule_no_match(self):
        a = _article(title="Cooking recipes", category="自动驾驶/3D感知")
        assert _passes_keyword_filter(a, {"自动驾驶/3D感知": ["lidar", "detection"]}) is False

    def test_global_wildcard_rule(self):
        a = _article(title="GPT-5 released", category="行业风向标")
        assert _passes_keyword_filter(a, {"*": ["gpt", "llm"]}) is True

    def test_category_rule_takes_priority_over_wildcard(self):
        a = _article(title="LiDAR paper", category="自动驾驶/3D感知")
        assert _passes_keyword_filter(
            a, {"自动驾驶/3D感知": ["lidar"], "*": ["cooking"]}
        ) is True

    def test_case_insensitive(self):
        a = _article(title="LIDAR Detection")
        assert _passes_keyword_filter(a, {"A": ["lidar"]}) is True

    def test_summary_also_checked(self):
        a = _article(title="New paper", rss_summary="autonomous driving benchmark", category="A")
        assert _passes_keyword_filter(a, {"A": ["autonomous"]}) is True
