# -*- coding: utf-8 -*-
"""Tech Blog Monitor source adapter tests."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from products.tech_blog_monitor.config import DEFAULT_FEEDS, FeedSource, TechBlogMonitorConfig
from products.tech_blog_monitor.content_fetcher import fetch_article_content
from products.tech_blog_monitor.fetcher import (
    Article,
    fetch_all,
    get_default_source_adapters,
)
from products.tech_blog_monitor.source_adapters import ChangelogAdapter, GitHubReleasesAdapter

_UTC = timezone.utc


def _fixture_json(name: str) -> object:
    path = Path(__file__).parent / "fixtures" / "source_adapters" / name
    return json.loads(path.read_text(encoding="utf-8"))


def _fixture_html(name: str) -> str:
    path = Path(__file__).parent / "fixtures" / name
    if not path.exists():
        path = Path(__file__).parent / "fixtures" / "source_adapters" / name
    return path.read_text(encoding="utf-8")


def _json_response(payload: object):
    response = SimpleNamespace()
    response.json = lambda: payload
    response.raise_for_status = lambda: None
    return response


def _text_response(payload: str):
    response = SimpleNamespace()
    response.content = payload.encode("utf-8")
    response.text = payload
    response.raise_for_status = lambda: None
    return response


def _failing_response(message: str):
    response = SimpleNamespace()

    def _raise() -> None:
        raise RuntimeError(message)

    response.raise_for_status = _raise
    response.json = lambda: {}
    return response


def _source(
    name: str,
    url: str,
    *,
    source_type: str,
    category: str = "AI Agent/工程实践",
    metadata: dict | None = None,
) -> FeedSource:
    return FeedSource(
        name=name,
        url=url,
        category=category,
        source_type=source_type,
        metadata=metadata or {},
    )


def _article(
    *,
    title: str,
    url: str,
    source_name: str,
    category: str = "AI Agent/工程实践",
    published: datetime | None = None,
) -> Article:
    return Article(
        title=title,
        url=url,
        source_name=source_name,
        category=category,
        source_id=f"{source_name}::{url}",
        rss_summary="summary",
        published=published,
        published_ts=int(published.timestamp()) if published else None,
        fetched_at=1744243200,
    )


def test_default_source_adapters_include_non_rss_types():
    adapters = get_default_source_adapters()
    assert set(adapters) >= {"rss", "github_releases", "changelog"}


def test_default_catalog_enables_high_priority_agent_release_sources():
    enabled_non_rss = [feed for feed in DEFAULT_FEEDS if feed.enabled and feed.source_type != "rss"]
    assert {feed.name for feed in enabled_non_rss} >= {
        "uv Releases",
        "OpenAI Agents Python Releases",
        "browser-use Releases",
        "Gemini CLI Releases",
        "Goose Releases",
        "FastAPI Release History",
    }
    assert len(enabled_non_rss) >= 6


def test_github_releases_adapter_normalizes_releases():
    adapter = GitHubReleasesAdapter()
    source = _source(
        "uv Releases",
        "https://api.github.com/repos/astral-sh/uv/releases",
        source_type="github_releases",
    )

    articles, health = adapter.fetch(
        source,
        max_articles=5,
        session=SimpleNamespace(get=lambda *args, **kwargs: _json_response(_fixture_json("github_releases.json"))),
    )

    assert health.success is True
    assert health.source_type == "github_releases"
    assert [article.title for article in articles] == ["uv 0.8.0", "uv 0.7.9"]
    assert all(article.url.startswith("https://github.com/astral-sh/uv/releases/tag/") for article in articles)
    assert all(article.source_name == "uv Releases" for article in articles)


def test_github_releases_adapter_reports_health_error():
    adapter = GitHubReleasesAdapter()
    source = _source(
        "uv Releases",
        "https://api.github.com/repos/astral-sh/uv/releases",
        source_type="github_releases",
    )

    articles, health = adapter.fetch(
        source,
        max_articles=5,
        session=SimpleNamespace(get=lambda *args, **kwargs: _failing_response("rate limited")),
    )

    assert articles == []
    assert health.success is False
    assert "rate limited" in health.error
    assert health.source_type == "github_releases"


def test_changelog_adapter_parses_generic_items():
    adapter = ChangelogAdapter()
    source = _source(
        "Python Release Notes",
        "https://example.com/python/releases.json",
        source_type="changelog",
    )

    articles, health = adapter.fetch(
        source,
        max_articles=5,
        session=SimpleNamespace(get=lambda *args, **kwargs: _json_response(_fixture_json("changelog_items.json"))),
    )

    assert health.success is True
    assert health.article_count == 2
    assert articles[0].title == "Python 3.14 beta 1"
    assert articles[0].rss_summary.startswith("First beta")
    assert articles[1].url.endswith("python-3132/")


def test_changelog_adapter_parses_pypi_release_history():
    adapter = ChangelogAdapter()
    source = _source(
        "FastAPI Release History",
        "https://pypi.org/pypi/fastapi/json",
        source_type="changelog",
        metadata={"format": "pypi"},
    )

    articles, health = adapter.fetch(
        source,
        max_articles=5,
        session=SimpleNamespace(get=lambda *args, **kwargs: _json_response(_fixture_json("pypi_release_history.json"))),
    )

    assert health.success is True
    assert [article.title for article in articles] == ["fastapi 0.116.0", "fastapi 0.115.2"]
    assert articles[0].url == "https://pypi.org/project/fastapi/0.116.0/"
    assert articles[0].published_ts > articles[1].published_ts


def test_changelog_adapter_reports_invalid_payload():
    adapter = ChangelogAdapter()
    source = _source(
        "Broken Changelog",
        "https://example.com/changelog.json",
        source_type="changelog",
    )

    articles, health = adapter.fetch(
        source,
        max_articles=5,
        session=SimpleNamespace(get=lambda *args, **kwargs: _json_response({"items": "bad"})),
    )

    assert articles == []
    assert health.success is False
    assert "items_key" in health.error


def test_fetch_all_aggregates_non_rss_sources(monkeypatch):
    payloads = {
        "https://api.github.com/repos/astral-sh/uv/releases": _fixture_json("github_releases.json"),
        "https://example.com/python/releases.json": _fixture_json("changelog_items.json"),
    }

    def _mock_session_get(self, url, **kwargs):
        return _json_response(payloads[url])

    monkeypatch.setattr("products.tech_blog_monitor.fetcher.requests.Session.get", _mock_session_get)

    config = TechBlogMonitorConfig(
        feeds=[
            _source(
                "uv Releases",
                "https://api.github.com/repos/astral-sh/uv/releases",
                source_type="github_releases",
            ),
            _source(
                "Python Release Notes",
                "https://example.com/python/releases.json",
                source_type="changelog",
            ),
        ],
        max_articles_per_feed=5,
        max_age_days=0,
    )

    articles, health_list = fetch_all(config)

    assert len(articles) == 4
    assert {health.source_type for health in health_list} == {"github_releases", "changelog"}
    assert {article.source_name for article in articles} == {"uv Releases", "Python Release Notes"}


def test_non_rss_sources_contribute_at_least_twenty_percent_of_daily_articles(monkeypatch):
    payload_by_url = {
        "https://openai.com/news/rss.xml": _fixture_html("rss_openai.xml"),
        "https://pytorch.org/blog/feed/": _fixture_html("rss_pytorch.xml"),
        "https://api.github.com/repos/astral-sh/uv/releases": _fixture_json("github_releases.json"),
        "https://pypi.org/pypi/fastapi/json": _fixture_json("pypi_release_history.json"),
    }

    def _mock_session_get(self, url, **kwargs):
        payload = payload_by_url[url]
        if isinstance(payload, str):
            return _text_response(payload)
        return _json_response(payload)

    monkeypatch.setattr("products.tech_blog_monitor.fetcher.requests.Session.get", _mock_session_get)

    sources = [
        FeedSource("OpenAI News", "https://openai.com/news/rss.xml", "行业风向标"),
        FeedSource("PyTorch Blog", "https://pytorch.org/blog/feed/", "深度技术"),
        FeedSource("uv Releases", "https://api.github.com/repos/astral-sh/uv/releases", "AI Agent/工程实践", source_type="github_releases"),
        FeedSource(
            "FastAPI Release History",
            "https://pypi.org/pypi/fastapi/json",
            "AI Agent/工程实践",
            source_type="changelog",
            metadata={"format": "pypi"},
        ),
    ]
    config = TechBlogMonitorConfig(feeds=sources, max_articles_per_feed=10, max_age_days=0)

    articles, health_list = fetch_all(config)
    source_type_by_name = {source.name: source.source_type for source in sources}
    non_rss_count = sum(1 for article in articles if source_type_by_name[article.source_name] != "rss")
    share = non_rss_count / len(articles)

    assert all(health.success for health in health_list)
    assert len(articles) == 8
    assert share >= 0.2


def test_non_rss_content_success_rate_matches_rss_baseline_from_source_specific_pages():
    github_source = _source(
        "uv Releases",
        "https://api.github.com/repos/astral-sh/uv/releases",
        source_type="github_releases",
    )
    changelog_source = _source(
        "FastAPI Release History",
        "https://pypi.org/pypi/fastapi/json",
        source_type="changelog",
        metadata={"format": "pypi"},
    )

    github_articles, github_health = GitHubReleasesAdapter().fetch(
        github_source,
        max_articles=1,
        session=SimpleNamespace(get=lambda *args, **kwargs: _json_response(_fixture_json("github_releases.json"))),
    )
    changelog_articles, changelog_health = ChangelogAdapter().fetch(
        changelog_source,
        max_articles=1,
        session=SimpleNamespace(get=lambda *args, **kwargs: _json_response(_fixture_json("pypi_release_history.json"))),
    )
    assert github_health.success and changelog_health.success

    html_by_url = {
        "https://rss.example.com/1": _fixture_html("article_page.html"),
        "https://rss.example.com/2": _fixture_html("json_ld_page.html"),
        github_articles[0].url: _fixture_html("github_release_page.html"),
        changelog_articles[0].url: _fixture_html("pypi_release_page.html"),
    }

    def _get(url, **kwargs):
        return SimpleNamespace(
            text=html_by_url[url],
            status_code=200,
            url=url,
        )

    requester = SimpleNamespace(get=_get)
    baseline_articles = [
        _article(title="RSS 1", url="https://rss.example.com/1", source_name="OpenAI News"),
        _article(title="RSS 2", url="https://rss.example.com/2", source_name="PyTorch Blog"),
    ]
    new_source_articles = [github_articles[0], changelog_articles[0]]

    baseline_results = [
        fetch_article_content(article, requester=requester, playwright_fallback=False)
        for article in baseline_articles
    ]
    new_source_results = [
        fetch_article_content(article, requester=requester, playwright_fallback=False)
        for article in new_source_articles
    ]

    baseline_success = sum(1 for item in baseline_results if item.content_status == "fetched") / len(baseline_results)
    new_source_success = sum(1 for item in new_source_results if item.content_status == "fetched") / len(new_source_results)

    assert new_source_success >= baseline_success * 0.95
