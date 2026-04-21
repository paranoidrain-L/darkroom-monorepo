"""Tech Blog Monitor API tests."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest

from products.tech_blog_monitor.api.app import app
from products.tech_blog_monitor.archive_store import ArchiveStore
from products.tech_blog_monitor.db.engine import build_sqlite_url
from products.tech_blog_monitor.db.schema_manager import bootstrap_schema
from products.tech_blog_monitor.fetcher import Article
from products.tech_blog_monitor.repository_provider import open_repository_bundle


def _article(
    title: str,
    url: str,
    source_name: str,
    category: str,
    published_ts: int,
    topic: str = "智能体",
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
    article.tags = [topic, "agent"]
    article.key_points = [f"{title} point"]
    article.recommended_for = ["工程师"]
    article.enrichment_status = "enriched"
    article.relevance_score = 4.2
    article.relevance_level = "medium"
    article.relevance_reasons = [f"dependency:{topic} 命中 summary"]
    article.matched_signals = [{"signal_name": topic, "signal_kind": "topic"}]
    article.dependency_match_score = 2.5
    article.topic_match_score = 1.1
    article.source_priority_score = 0.6
    return article


def _build_store(tmp_path):
    db_path = tmp_path / "assets.db"
    article_one = _article(
        title="Agent Systems at Scale",
        url="https://example.com/agent",
        source_name="OpenAI News",
        category="AI Agent/工程实践",
        published_ts=1744588800,
    )
    article_two = _article(
        title="Infra Signals",
        url="https://example.com/infra",
        source_name="NVIDIA Technical Blog",
        category="深度技术",
        published_ts=1744502400,
        topic="基础设施",
    )

    with ArchiveStore(str(db_path)) as store:
        run_id = store.record_run(
            generated_at=1744675200,
            generated_at_iso="2025-04-15T00:00:00+00:00",
            output_path="/tmp/report.md",
            view="by_category",
            incremental_mode="split",
            all_articles=[article_one, article_two],
            report_articles=[article_one, article_two],
            new_urls={article_one.url},
        )
        article_id = store.get_article_by_url(article_one.url)["article_id"]

    return str(db_path), run_id, article_id


def _insert_ops_task(db_path: str) -> None:
    bootstrap_schema(build_sqlite_url(db_path))
    with open_repository_bundle(asset_db_path=db_path) as bundle:
        bundle.task_repository.create_task(
            task_id="task_ops_1",
            task_type="manual_run",
            task_status="succeeded",
            trigger_source="cli",
            requested_by="cli",
            idempotency_key="ops:1",
            scope="report:/tmp/report.md",
            artifact_uri="/tmp/report.md",
            input_payload={"output_path": "/tmp/report.md"},
            result_payload={
                "exit_code": 0,
                "run_summary": {
                    "duration_ms": 1000,
                    "feed_stats": {"success": 2, "failure": 0, "disabled": 0},
                    "content_status_counts": {"fetched": 2},
                    "enrichment_status_counts": {"enriched": 2},
                    "delivery_status_counts": {"delivered": 1},
                    "status": "success",
                },
            },
            max_retries=0,
            retry_count=0,
            started_at=100,
            finished_at=120,
        )


@pytest.mark.anyio
async def test_health_does_not_require_asset_db():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.anyio
async def test_articles_requires_asset_db_path(monkeypatch):
    monkeypatch.delenv("TECH_BLOG_ASSET_DB_PATH", raising=False)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/articles")
    assert response.status_code == 503
    assert "asset db not configured" in response.json()["detail"]


@pytest.mark.anyio
async def test_search_requires_asset_db_path(monkeypatch):
    monkeypatch.delenv("TECH_BLOG_ASSET_DB_PATH", raising=False)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/search", params={"query": "agent"})
    assert response.status_code == 503
    assert "asset db not configured" in response.json()["detail"]


@pytest.mark.anyio
async def test_runs_and_run_detail(monkeypatch, tmp_path):
    db_path, run_id, _ = _build_store(tmp_path)
    monkeypatch.setenv("TECH_BLOG_ASSET_DB_PATH", db_path)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        runs = await client.get("/runs")
        detail = await client.get(f"/runs/{run_id}")
    assert runs.status_code == 200
    assert runs.json()["items"][0]["run_id"] == run_id
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["run"]["run_id"] == run_id
    assert len(payload["articles"]) == 2


@pytest.mark.anyio
async def test_articles_and_article_detail(monkeypatch, tmp_path):
    db_path, _, article_id = _build_store(tmp_path)
    monkeypatch.setenv("TECH_BLOG_ASSET_DB_PATH", db_path)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        articles = await client.get("/articles", params={"source_name": "OpenAI News"})
        article = await client.get(f"/articles/{article_id}")
    assert articles.status_code == 200
    assert len(articles.json()["items"]) == 1
    assert articles.json()["items"][0]["relevance_level"] == "medium"
    assert article.status_code == 200
    assert article.json()["article"]["article_id"] == article_id
    assert article.json()["article"]["relevance_score"] == 4.2


@pytest.mark.anyio
async def test_search_and_insights(monkeypatch, tmp_path):
    db_path, _, _ = _build_store(tmp_path)
    monkeypatch.setenv("TECH_BLOG_ASSET_DB_PATH", db_path)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        search = await client.get("/search", params={"query": "agent", "limit": 5})
        insights = await client.get(
            "/insights",
            params={"days": 14, "top_k": 5, "max_articles": 100},
        )
    assert search.status_code == 200
    assert search.json()["items"][0]["title"] == "Agent Systems at Scale"
    assert search.json()["items"][0]["relevance_level"] == "medium"
    assert insights.status_code == 200
    payload = insights.json()
    assert payload["status"] in {"ok", "insufficient_data", "low_signal", "unbalanced_sources"}
    assert "topic_clusters" in payload


@pytest.mark.anyio
async def test_ops_summary(monkeypatch, tmp_path):
    db_path, _, _ = _build_store(tmp_path)
    _insert_ops_task(db_path)
    monkeypatch.setenv("TECH_BLOG_ASSET_DB_PATH", db_path)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/ops/summary", params={"limit": 10})

    assert response.status_code == 200
    payload = response.json()
    assert payload["window_size"] >= 1
    kpis = {item["name"]: item for item in payload["kpis"]}
    assert kpis["run_success_rate"]["value"] == 1.0


@pytest.mark.anyio
async def test_ops_summary_uses_database_url_when_configured(monkeypatch, tmp_path):
    db_path, _, _ = _build_store(tmp_path)
    _insert_ops_task(db_path)
    monkeypatch.delenv("TECH_BLOG_ASSET_DB_PATH", raising=False)
    monkeypatch.setenv("TECH_BLOG_DATABASE_URL", build_sqlite_url(db_path))
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/ops/summary", params={"limit": 10})

    assert response.status_code == 200
    payload = response.json()
    assert payload["window_size"] >= 1
    kpis = {item["name"]: item for item in payload["kpis"]}
    assert kpis["run_success_rate"]["value"] == 1.0


@pytest.mark.anyio
async def test_feedback_endpoint(monkeypatch, tmp_path):
    db_path, run_id, _ = _build_store(tmp_path)
    monkeypatch.setenv("TECH_BLOG_ASSET_DB_PATH", db_path)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/feedback",
            json={
                "run_id": run_id,
                "role": "engineer",
                "feedback_type": "thumbs_up",
                "feedback_text": "搜索结果可用",
                "metadata": {"source": "api"},
                "created_at": 1744675300,
            },
        )
    assert response.status_code == 201
    payload = response.json()
    assert payload["feedback_id"].startswith("feedback_")

    with ArchiveStore(db_path) as store:
        rows = store.list_feedback(run_id=run_id)
    assert rows[0]["metadata"]["source"] == "api"


@pytest.mark.anyio
async def test_api_uses_database_url_when_configured(monkeypatch, tmp_path):
    db_path, _, _ = _build_store(tmp_path)
    monkeypatch.delenv("TECH_BLOG_ASSET_DB_PATH", raising=False)
    monkeypatch.setenv("TECH_BLOG_DATABASE_URL", build_sqlite_url(db_path))
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        articles = await client.get("/articles")
        search = await client.get("/search", params={"query": "agent"})

    assert articles.status_code == 200
    assert articles.json()["items"][0]["title"] == "Agent Systems at Scale"
    assert search.status_code == 200
    assert search.json()["items"][0]["title"] == "Agent Systems at Scale"
