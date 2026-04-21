# -*- coding: utf-8 -*-
"""Internal relevance tests."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from products.tech_blog_monitor.fetcher import Article
from products.tech_blog_monitor.internal_relevance import (
    evaluate_internal_relevance,
    load_stack_profile,
    scan_repo_roots,
)
from products.tech_blog_monitor.internal_relevance.models import StackProfile, StackSignal

_UTC = timezone.utc
_FIXTURES = Path(__file__).parent / "fixtures"


def _article(
    *,
    title: str,
    url: str,
    source_name: str = "OpenAI News",
    source_type: str = "rss",
    topic: str = "",
    tags: list[str] | None = None,
    rss_summary: str = "",
    ai_summary: str = "",
    one_line_summary: str = "",
    why_it_matters: str = "",
    clean_text: str = "",
    published_ts: int = 1744588800,
) -> Article:
    published = datetime.fromtimestamp(published_ts, tz=_UTC)
    article = Article(
        title=title,
        url=url,
        source_name=source_name,
        source_type=source_type,
        category="AI Agent/工程实践",
        source_id=f"{source_name}::{url}",
        rss_summary=rss_summary,
        published=published,
        published_ts=published_ts,
        fetched_at=published_ts,
        clean_text=clean_text,
        content_status="fetched" if clean_text else "not_fetched",
        content_source="html_article" if clean_text else "",
    )
    article.ai_summary = ai_summary
    article.one_line_summary = one_line_summary
    article.why_it_matters = why_it_matters
    article.topic = topic
    article.tags = list(tags or [])
    article.enrichment_status = "enriched"
    return article


def _fixture_json(name: str) -> dict:
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))


def test_load_stack_profile_reads_signals_and_source_priorities(tmp_path):
    profile_path = tmp_path / "stack_profile.yaml"
    profile_path.write_text(
        """
name: test-profile
dependencies:
  - name: fastapi
    aliases: [starlette]
    weight: 1.5
topics:
  - name: ai_agents
    keywords: [agent orchestration, tool calling]
    weight: 1.2
source_priorities:
  github_releases: 1.8
""",
        encoding="utf-8",
    )

    profile = load_stack_profile(str(profile_path))

    assert profile.profile_name == "test-profile"
    assert {signal.name for signal in profile.dependency_signals()} == {"fastapi"}
    assert profile.topic_signals()[0].keywords == ["agent orchestration", "tool calling"]
    assert profile.source_priorities["github_releases"] == 1.8


def test_scan_repo_roots_supports_requirements_pyproject_and_package_json(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "requirements.txt").write_text("fastapi==0.110.0\nuvicorn>=0.30\n", encoding="utf-8")
    (repo_root / "pyproject.toml").write_text(
        """
[project]
dependencies = ["pydantic>=2", "sqlalchemy>=2"]
""",
        encoding="utf-8",
    )
    frontend = repo_root / "frontend"
    frontend.mkdir()
    (frontend / "package.json").write_text(
        json.dumps(
            {
                "dependencies": {"react": "^18.0.0"},
                "devDependencies": {"typescript": "^5.0.0"},
            }
        ),
        encoding="utf-8",
    )

    result = scan_repo_roots([str(repo_root)])

    names = {signal.name for signal in result.signals}
    assert {"fastapi", "uvicorn", "pydantic", "sqlalchemy", "react", "typescript"} <= names
    assert len(result.scanned_files) == 3


def test_evaluate_internal_relevance_scores_article_and_builds_reasons():
    profile = StackProfile(
        signals=[
            StackSignal(
                signal_id="dep_fastapi",
                name="fastapi",
                kind="dependency",
                aliases=["fastapi", "starlette"],
                weight=1.5,
                source="profile",
            ),
            StackSignal(
                signal_id="topic_agents",
                name="ai_agents",
                kind="topic",
                keywords=["agent orchestration", "tool calling"],
                weight=1.2,
                source="profile",
            ),
        ],
        source_priorities={"github_releases": 1.5, "rss": 0.6},
    )
    article = _article(
        title="FastAPI agent orchestration patterns",
        url="https://example.com/fastapi-agent",
        topic="tool calling",
        tags=["fastapi", "agents"],
        one_line_summary="FastAPI services now support agent orchestration.",
        clean_text="This article explains FastAPI APIs for tool calling and workflow state.",
        source_type="github_releases",
        source_name="uv Releases",
    )

    scored_articles, report = evaluate_internal_relevance(
        [article],
        profile=profile,
        scanned_signals=[],
        scanned_repo_roots=[],
        scanned_manifest_count=0,
        warnings=[],
    )

    scored = scored_articles[0]
    assert scored.relevance_score > 0
    assert scored.relevance_level in {"medium", "high"}
    assert scored.dependency_match_score > 0
    assert scored.topic_match_score > 0
    assert scored.source_priority_score == 1.5
    assert any("dependency:fastapi" in reason for reason in scored.relevance_reasons)
    assert any(item["signal_name"] == "fastapi" for item in scored.matched_signals)
    assert report.matched_article_count == 1


def test_internal_relevance_eval_recall_at_10():
    profile = load_stack_profile(str(_FIXTURES / "internal_relevance_eval_profile.yaml"))
    eval_corpus = _fixture_json("internal_relevance_eval_corpus.json")
    articles = [_article(**item) for item in eval_corpus["articles"]]
    relevant_urls = set(eval_corpus["relevant_urls"])

    scored_articles, _ = evaluate_internal_relevance(
        articles,
        profile=profile,
        scanned_signals=[],
        scanned_repo_roots=[],
        scanned_manifest_count=0,
        warnings=[],
    )
    top_10_urls = {
        article.url
        for article in sorted(
            scored_articles,
            key=lambda item: (item.relevance_score, item.published_ts or 0),
            reverse=True,
        )[:10]
    }
    recall_at_10 = len(top_10_urls & relevant_urls) / len(relevant_urls)

    assert recall_at_10 >= 0.8


def test_internal_relevance_stably_skips_without_inputs():
    article = _article(title="Unrelated", url="https://example.com/skip")

    scored_articles, report = evaluate_internal_relevance(
        [article],
        profile=StackProfile(source_priorities={"rss": 0.6}),
        scanned_signals=[],
        scanned_repo_roots=[],
        scanned_manifest_count=0,
        warnings=[],
    )

    assert scored_articles[0].relevance_level == "not_evaluated"
    assert report.status == "skipped"
