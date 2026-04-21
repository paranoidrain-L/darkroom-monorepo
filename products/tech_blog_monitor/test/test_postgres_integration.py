# -*- coding: utf-8 -*-
"""Optional PostgreSQL integration tests for P1."""

from __future__ import annotations

import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from products.tech_blog_monitor.archive_store import ArchiveStore
from products.tech_blog_monitor.db.schema_manager import mirror_sqlite_asset_db
from products.tech_blog_monitor.fetcher import Article
from products.tech_blog_monitor.repository_provider import open_repository_bundle

_ROOT = Path(__file__).resolve().parents[3]
_VENV_PYTHON = _ROOT / ".venv/bin/python3"
_ALEMBIC = _ROOT / ".venv/bin/alembic"
_PG_TEST_URL = os.environ.get("TECH_BLOG_PG_TEST_URL", "").strip()

pytestmark = pytest.mark.skipif(
    not _PG_TEST_URL,
    reason="requires TECH_BLOG_PG_TEST_URL pointing to a dedicated PostgreSQL test database",
)


def _build_store(tmp_path: Path) -> str:
    db_path = tmp_path / "assets.db"
    published = datetime(2025, 4, 15, tzinfo=timezone.utc)
    article = Article(
        title="Agent Memory Systems",
        url="https://example.com/agent-memory",
        source_name="OpenAI News",
        category="AI Agent/工程实践",
        source_id="OpenAI News::https://example.com/agent-memory",
        rss_summary="Agent memory summary",
        published=published,
        published_ts=int(published.timestamp()),
        fetched_at=int(published.timestamp()),
        clean_text="Persistent agent memory keeps workflow state across sessions.",
        content_status="fetched",
        content_source="html_article",
    )
    article.one_line_summary = "Agent memory summary"
    article.why_it_matters = "Useful for durable agent workflows."
    article.topic = "智能体"
    article.tags = ["agent", "memory"]
    article.key_points = ["state retention"]
    article.recommended_for = ["工程师"]
    article.enrichment_status = "enriched"

    baseline = Article(
        title="Agent Coordination Patterns",
        url="https://example.com/agent-coordination",
        source_name="NVIDIA Technical Blog",
        category="深度技术",
        source_id="NVIDIA Technical Blog::https://example.com/agent-coordination",
        rss_summary="Agent coordination memory summary",
        published=published,
        published_ts=int(published.timestamp()) - 600,
        fetched_at=int(published.timestamp()) - 600,
        clean_text="Shared memory can help an agent coordinator hand work across workers.",
        content_status="fetched",
        content_source="html_article",
    )
    baseline.one_line_summary = "Agent coordination memory summary"
    baseline.why_it_matters = "Relevant for orchestrating worker systems."
    baseline.topic = "智能体"
    baseline.tags = ["agent", "memory"]
    baseline.key_points = ["coordination"]
    baseline.recommended_for = ["工程师"]
    baseline.enrichment_status = "enriched"

    with ArchiveStore(str(db_path)) as store:
        store.record_run(
            generated_at=int(published.timestamp()),
            generated_at_iso="2025-04-15T00:00:00+00:00",
            output_path="/tmp/report.md",
            view="by_category",
            incremental_mode="split",
            all_articles=[article, baseline],
            report_articles=[article, baseline],
            new_urls={article.url},
        )
    return str(db_path)


def _run_alembic(*args: str) -> None:
    env = {
        **os.environ,
        "PYTHONPATH": str(_ROOT),
        "TECH_BLOG_DATABASE_URL": _PG_TEST_URL,
    }
    subprocess.run(
        [str(_VENV_PYTHON), str(_ALEMBIC), "-c", str(_ROOT / "alembic.ini"), *args],
        check=True,
        cwd=_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


def test_postgres_migration_and_repository_roundtrip(tmp_path):
    _run_alembic("upgrade", "head")
    _run_alembic("downgrade", "base")
    _run_alembic("upgrade", "head")

    sqlite_db = _build_store(tmp_path)
    mirror_sqlite_asset_db(sqlite_db, _PG_TEST_URL)

    with open_repository_bundle(database_url=_PG_TEST_URL) as bundle:
        search_rows = bundle.search_repository.search_articles(query="agent memory", limit=5)
        retrieval_rows = bundle.retrieval_repository.retrieve_chunks(
            question="How is workflow state preserved across sessions?",
            limit=5,
        )
        retrieval_rows_text = bundle.retrieval_repository.retrieve_chunks(
            question="How is workflow state preserved across sessions?",
            limit=5,
            embedding_provider_name="openai_compatible",
        )

    assert search_rows
    assert [row["url"] for row in search_rows[:2]] == [
        "https://example.com/agent-memory",
        "https://example.com/agent-coordination",
    ]
    assert retrieval_rows
    assert retrieval_rows[0]["url"] == "https://example.com/agent-memory"
    assert retrieval_rows_text
    assert retrieval_rows_text[0]["url"] == "https://example.com/agent-memory"
