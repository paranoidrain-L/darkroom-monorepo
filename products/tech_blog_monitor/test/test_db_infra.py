# -*- coding: utf-8 -*-
"""Tech Blog Monitor P1 DB infra tests."""

from __future__ import annotations

import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import inspect, select

from products.tech_blog_monitor.archive_store import ArchiveStore
from products.tech_blog_monitor.db.engine import (
    build_sqlite_url,
    create_engine_for_url,
    create_session_factory,
)
from products.tech_blog_monitor.db.models import (
    ArticleRelevanceModel,
    ArticleSearchDocumentModel,
    ChunkEmbeddingRecordModel,
)
from products.tech_blog_monitor.db.schema_manager import (
    backfill_article_search_documents,
    backfill_chunk_embedding_records,
    bootstrap_schema,
)
from products.tech_blog_monitor.fetcher import Article
from products.tech_blog_monitor.repository_provider import open_repository_bundle

_ROOT = Path(__file__).resolve().parents[3]
_VENV_PYTHON = _ROOT / ".venv/bin/python3"


def _article(
    *,
    title: str = "Agent Systems at Scale",
    url: str = "https://example.com/agent",
    source_name: str = "OpenAI News",
    category: str = "AI Agent/工程实践",
    published_ts: int = 1744588800,
    topic: str = "智能体",
) -> Article:
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
    article.relevance_score = 4.5
    article.relevance_level = "medium"
    article.relevance_reasons = [f"dependency:{title.split()[0].lower()} 命中 title"]
    article.matched_signals = [{"signal_name": title.split()[0].lower(), "signal_kind": "dependency"}]
    article.dependency_match_score = 3.3
    article.source_priority_score = 1.2
    return article


def _build_store(tmp_path: Path) -> tuple[str, str, str]:
    db_path = tmp_path / "assets.db"
    article = _article()
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
        article_id = store.get_article_by_url(article.url)["article_id"]
    return str(db_path), run_id, article_id


def test_repository_bundle_reads_archive_store_sqlite_and_commits_feedback(tmp_path):
    db_path, run_id, article_id = _build_store(tmp_path)

    with open_repository_bundle(asset_db_path=db_path) as bundle:
        assert bundle.run_repository.get_run(run_id)["run_id"] == run_id
        assert bundle.article_repository.get_article(article_id)["article_id"] == article_id
        assert bundle.article_repository.get_article(article_id)["relevance_level"] == "medium"
        feedback_id = bundle.feedback_repository.add_feedback(
            run_id=run_id,
            role="engineer",
            feedback_type="like",
            feedback_text="looks good",
            metadata={"source": "repository"},
            created_at=1744675300,
        )

    with ArchiveStore(db_path) as store:
        rows = store.list_feedback(run_id=run_id)
    assert rows[0]["feedback_id"] == feedback_id
    assert rows[0]["metadata"]["source"] == "repository"


def test_repository_bundle_prefers_database_url_over_asset_db_path(tmp_path):
    db_path, run_id, article_id = _build_store(tmp_path)

    with open_repository_bundle(
        asset_db_path=str(tmp_path / "missing.db"),
        database_url=build_sqlite_url(db_path),
    ) as bundle:
        assert bundle.run_repository.get_run(run_id)["run_id"] == run_id
        assert bundle.article_repository.get_article(article_id)["article_id"] == article_id


def test_schema_bootstrap_and_backfill_create_search_and_embedding_rows(tmp_path):
    db_path, _, _ = _build_store(tmp_path)
    database_url = build_sqlite_url(db_path)
    bootstrap_schema(database_url)

    session_factory = create_session_factory(database_url)
    with session_factory() as session:
        assert backfill_article_search_documents(session) == 1
        assert backfill_chunk_embedding_records(session) >= 1
        session.commit()

    with session_factory() as session:
        assert session.execute(select(ArticleRelevanceModel)).scalar_one().article_id
        assert session.execute(select(ArticleSearchDocumentModel)).scalar_one().article_id
        assert session.execute(select(ChunkEmbeddingRecordModel)).scalar_one().chunk_id


def test_alembic_upgrade_and_downgrade_sqlite(tmp_path):
    database_url = build_sqlite_url(str(tmp_path / "alembic.db"))
    env = {
        **os.environ,
        "PYTHONPATH": str(_ROOT),
        "TECH_BLOG_DATABASE_URL": database_url,
    }

    subprocess.run(
        [str(_VENV_PYTHON), str(_ROOT / ".venv/bin/alembic"), "-c", str(_ROOT / "alembic.ini"), "upgrade", "head"],
        check=True,
        cwd=_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    engine = create_engine_for_url(database_url)
    table_names = set(inspect(engine).get_table_names())
    assert {
        "runs",
        "articles",
        "article_relevances",
        "article_search_documents",
        "chunk_embedding_records",
    } <= table_names

    subprocess.run(
        [str(_VENV_PYTHON), str(_ROOT / ".venv/bin/alembic"), "-c", str(_ROOT / "alembic.ini"), "downgrade", "base"],
        check=True,
        cwd=_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    engine.dispose()
    downgraded_engine = create_engine_for_url(database_url)
    downgraded_table_names = set(inspect(downgraded_engine).get_table_names())
    assert "articles" not in downgraded_table_names
