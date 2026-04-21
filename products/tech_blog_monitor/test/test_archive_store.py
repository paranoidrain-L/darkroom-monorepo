# -*- coding: utf-8 -*-
"""Tech Blog Monitor archive_store 单元测试。"""

import json
import sqlite3
from datetime import datetime, timezone

import pytest

from products.tech_blog_monitor.archive_store import (
    ArchiveStore,
    _build_article_id,
    _build_content_hash,
    _normalize_url,
)
from products.tech_blog_monitor.fetcher import Article


def _article(
    title="Article A",
    url="https://example.com/a",
    source_name="Source A",
    category="行业风向标",
    rss_summary="raw summary",
    ai_summary="",
    published_ts=1744243200,
    fetched_at=1744243200,
):
    published = (
        datetime.fromtimestamp(published_ts, tz=timezone.utc)
        if published_ts is not None
        else None
    )
    return Article(
        title=title,
        url=url,
        source_name=source_name,
        category=category,
        source_id=f"{source_name}::{url}",
        rss_summary=rss_summary,
        published=published,
        published_ts=published_ts,
        fetched_at=fetched_at,
        ai_summary=ai_summary,
    )


def test_archive_store_initializes_schema(tmp_path):
    path = tmp_path / "assets.db"
    with ArchiveStore(str(path)) as store:
        assert store.schema_version() == 6
        assert store.count_rows("runs") == 0
        assert store.count_rows("articles") == 0
        assert store.count_rows("run_articles") == 0
        assert store.count_rows("article_contents") == 0
        assert store.count_rows("article_enrichments") == 0
        assert store.count_rows("article_relevances") == 0
        assert store.count_rows("article_chunks") == 0
        assert store.count_rows("deliveries") == 0
        assert store.count_rows("feedback") == 0


def test_record_run_persists_articles_and_run_snapshots(tmp_path):
    path = tmp_path / "assets.db"
    article = _article(ai_summary="AI 摘要")
    article.one_line_summary = "一句话总结"
    article.key_points = ["点1", "点2"]
    article.why_it_matters = "值得关注"
    article.recommended_for = ["工程师"]
    article.tags = ["agent"]
    article.topic = "智能体"
    article.enrichment_status = "enriched"
    article.relevance_score = 4.2
    article.relevance_level = "medium"
    article.relevance_reasons = ["dependency:fastapi 命中 title"]
    article.matched_signals = [{"signal_name": "fastapi", "signal_kind": "dependency"}]
    article.dependency_match_score = 3.0
    article.topic_match_score = 0.0
    article.source_priority_score = 1.2

    with ArchiveStore(str(path)) as store:
        run_id = store.record_run(
            generated_at=1744243200,
            generated_at_iso="2026-04-10T00:00:00+00:00",
            output_path="/tmp/report.md",
            view="by_category",
            incremental_mode="split",
            all_articles=[article],
            report_articles=[article],
            new_urls={article.url},
        )

        assert store.count_rows("runs") == 1
        assert store.count_rows("articles") == 1
        assert store.count_rows("run_articles") == 1
        assert store.count_rows("article_enrichments") == 1
        assert store.count_rows("article_relevances") == 1
        assert store.count_rows("article_chunks") >= 1

        run = store.get_run(run_id)
        assert run is not None
        assert run["article_count"] == 1
        assert run["new_article_count"] == 1

        saved = store.get_article_by_url(article.url)
        assert saved is not None
        assert saved["title"] == article.title
        assert saved["source_name"] == article.source_name
        assert saved["ai_summary"] == "AI 摘要"
        assert saved["content_status"] == "not_fetched"
        assert saved["one_line_summary"] == "一句话总结"
        assert saved["key_points"] == ["点1", "点2"]
        assert saved["recommended_for"] == ["工程师"]
        assert saved["tags"] == ["agent"]
        assert saved["topic"] == "智能体"
        assert saved["enrichment_status"] == "enriched"
        assert saved["relevance_score"] == 4.2
        assert saved["relevance_level"] == "medium"
        assert saved["relevance_reasons"] == ["dependency:fastapi 命中 title"]

        snapshots = store.list_run_articles(run_id)
        assert len(snapshots) == 1
        assert snapshots[0]["is_new"] == 1
        assert snapshots[0]["in_report"] == 1
        assert snapshots[0]["report_position"] == 0

        chunks = store.retrieve_chunks(question="一句话")
        assert chunks
        assert chunks[0]["url"] == article.url
        assert chunks[0]["source_kind"] in {"clean_text", "summary_fallback"}


def test_record_run_upserts_article_across_runs(tmp_path):
    path = tmp_path / "assets.db"
    first = _article(ai_summary="")
    second = _article(ai_summary="新的 AI 摘要", fetched_at=1744329600)

    with ArchiveStore(str(path)) as store:
        store.record_run(
            generated_at=1744243200,
            generated_at_iso="2026-04-10T00:00:00+00:00",
            output_path="/tmp/report1.md",
            view="by_category",
            incremental_mode="split",
            all_articles=[first],
            report_articles=[first],
            new_urls={first.url},
        )
        store.record_run(
            generated_at=1744329600,
            generated_at_iso="2026-04-11T00:00:00+00:00",
            output_path="/tmp/report2.md",
            view="by_time",
            incremental_mode="new_only",
            all_articles=[second],
            report_articles=[second],
            new_urls=set(),
        )

        assert store.count_rows("runs") == 2
        assert store.count_rows("articles") == 1
        assert store.count_rows("run_articles") == 2

        saved = store.get_article_by_url(first.url)
        assert saved is not None
        assert saved["first_seen_at"] == 1744243200
        assert saved["last_seen_at"] == 1744329600
        assert saved["latest_fetched_at"] == 1744329600
        assert saved["ai_summary"] == "新的 AI 摘要"


def test_list_articles_supports_filters(tmp_path):
    path = tmp_path / "assets.db"
    a1 = _article(url="https://example.com/a", source_name="Source A", category="行业风向标")
    a2 = _article(url="https://example.com/b", source_name="Source B", category="深度技术")

    with ArchiveStore(str(path)) as store:
        store.record_run(
            generated_at=1744243200,
            generated_at_iso="2026-04-10T00:00:00+00:00",
            output_path="/tmp/report.md",
            view="by_category",
            incremental_mode="split",
            all_articles=[a1, a2],
            report_articles=[a1, a2],
            new_urls={a1.url, a2.url},
        )

        assert len(store.list_recent_articles()) == 2
        assert len(store.list_articles(source_name="Source A")) == 1
        assert len(store.list_articles(category="深度技术")) == 1


def test_get_article_and_list_runs_read_helpers(tmp_path):
    path = tmp_path / "assets.db"
    first = _article(url="https://example.com/a", fetched_at=1744243200)
    second = _article(url="https://example.com/b", fetched_at=1744329600)

    with ArchiveStore(str(path)) as store:
        run_one = store.record_run(
            generated_at=1744243200,
            generated_at_iso="2026-04-10T00:00:00+00:00",
            output_path="/tmp/report1.md",
            view="by_category",
            incremental_mode="split",
            all_articles=[first],
            report_articles=[first],
            new_urls={first.url},
        )
        run_two = store.record_run(
            generated_at=1744329600,
            generated_at_iso="2026-04-11T00:00:00+00:00",
            output_path="/tmp/report2.md",
            view="by_time",
            incremental_mode="split",
            all_articles=[second],
            report_articles=[second],
            new_urls={second.url},
        )

        second_article = store.get_article_by_url(second.url)
        assert second_article is not None
        by_id = store.get_article(second_article["article_id"])
        assert by_id is not None
        assert by_id["url"] == second.url

        runs = store.list_runs(limit=10)
        assert [item["run_id"] for item in runs] == [run_two, run_one]


def test_article_id_is_stable_for_normalized_url():
    normalized = _normalize_url("HTTPS://Example.com/path#fragment")
    assert normalized == "https://example.com/path"
    assert _build_article_id(normalized) == _build_article_id("https://example.com/path")


def test_content_hash_is_stable_for_same_article_content():
    left = _article(
        url="https://example.com/a",
        title="Same Title",
        source_name="Source A",
        rss_summary="same summary",
        fetched_at=1,
        ai_summary="",
    )
    right = _article(
        url="https://example.com/a",
        title="Same Title",
        source_name="Source A",
        rss_summary="same summary",
        fetched_at=999,
        ai_summary="different ai summary should not matter",
    )
    assert _build_content_hash(left) == _build_content_hash(right)


def test_import_state_file_reads_legacy_state(tmp_path):
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({"https://example.com/a": 1000}), encoding="utf-8")

    with ArchiveStore(str(tmp_path / "assets.db")) as store:
        imported = store.import_state_file(str(state_path))
        assert imported == 1
        saved = store.get_article_by_url("https://example.com/a")
        assert saved is not None
        assert saved["first_seen_at"] == 1000


def test_ingest_archive_payload_reads_current_json_format(tmp_path):
    payload = {
        "generated_at": 1744243200,
        "generated_at_iso": "2026-04-10T00:00:00+00:00",
        "view": "by_category",
        "incremental_mode": "split",
        "articles": [
            {
                "title": "Article A",
                "url": "https://example.com/a",
                "source_name": "Source A",
                "category": "行业风向标",
                "source_id": "Source A::https://example.com/a",
                "published_ts": 1744243200,
                "fetched_at": 1744243200,
                "rss_summary": "raw summary",
                "ai_summary": "AI 摘要",
            }
        ],
        "new_articles": [
            {"url": "https://example.com/a"}
        ],
    }

    with ArchiveStore(str(tmp_path / "assets.db")) as store:
        run_id = store.ingest_archive_payload(payload, output_path="/tmp/report.json")
        assert run_id
        assert store.count_rows("runs") == 1
        assert store.count_rows("articles") == 1
        assert store.count_rows("article_contents") == 1
        snapshots = store.list_run_articles(run_id)
        assert snapshots[0]["is_new"] == 1
        assert snapshots[0]["in_report"] == 1
        assert snapshots[0]["report_position"] == 0


def test_ingest_archive_payload_preserves_all_articles_vs_report_articles(tmp_path):
    payload = {
        "generated_at": 1744243200,
        "generated_at_iso": "2026-04-10T00:00:00+00:00",
        "view": "by_category",
        "incremental_mode": "split",
        "articles": [
            {
                "title": "Article A",
                "url": "https://example.com/a",
                "source_name": "Source A",
                "category": "行业风向标",
                "source_id": "Source A::https://example.com/a",
                "published_ts": 1744243200,
                "fetched_at": 1744243200,
                "rss_summary": "raw summary a",
                "ai_summary": "AI 摘要 A",
            }
        ],
        "all_articles": [
            {
                "title": "Article A",
                "url": "https://example.com/a",
                "source_name": "Source A",
                "category": "行业风向标",
                "source_id": "Source A::https://example.com/a",
                "published_ts": 1744243200,
                "fetched_at": 1744243200,
                "rss_summary": "raw summary a",
                "ai_summary": "AI 摘要 A",
            },
            {
                "title": "Article B",
                "url": "https://example.com/b",
                "source_name": "Source B",
                "category": "深度技术",
                "source_id": "Source B::https://example.com/b",
                "published_ts": 1744243201,
                "fetched_at": 1744243201,
                "rss_summary": "raw summary b",
                "ai_summary": "AI 摘要 B",
            },
        ],
        "new_articles": [{"url": "https://example.com/a"}],
    }

    with ArchiveStore(str(tmp_path / "assets.db")) as store:
        run_id = store.ingest_archive_payload(payload, output_path="/tmp/report.json")
        run = store.get_run(run_id)
        assert run is not None
        assert run["article_count"] == 1
        assert run["all_article_count"] == 2
        assert run["new_article_count"] == 1

        snapshots = {
            row["url"]: row
            for row in store.list_run_articles(run_id)
        }
        assert snapshots["https://example.com/a"]["in_report"] == 1
        assert snapshots["https://example.com/a"]["report_position"] == 0
        assert snapshots["https://example.com/b"]["in_report"] == 0
        assert snapshots["https://example.com/b"]["report_position"] is None


def test_archive_store_migrates_v1_to_v2(tmp_path):
    path = tmp_path / "assets.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT INTO meta(key, value) VALUES ('schema_version', '1');
        CREATE TABLE runs (
            run_id TEXT PRIMARY KEY,
            generated_at INTEGER NOT NULL,
            generated_at_iso TEXT NOT NULL,
            output_path TEXT NOT NULL,
            view TEXT NOT NULL,
            incremental_mode TEXT NOT NULL,
            article_count INTEGER NOT NULL,
            all_article_count INTEGER NOT NULL,
            new_article_count INTEGER NOT NULL
        );
        CREATE TABLE articles (
            article_id TEXT PRIMARY KEY,
            normalized_url TEXT NOT NULL UNIQUE,
            url TEXT NOT NULL,
            source_id TEXT NOT NULL,
            source_name TEXT NOT NULL,
            category TEXT NOT NULL,
            title TEXT NOT NULL,
            published_ts INTEGER,
            first_seen_at INTEGER NOT NULL,
            last_seen_at INTEGER NOT NULL,
            latest_fetched_at INTEGER NOT NULL,
            rss_summary TEXT NOT NULL DEFAULT '',
            ai_summary TEXT NOT NULL DEFAULT '',
            content_hash TEXT NOT NULL,
            last_run_id TEXT,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        );
        CREATE TABLE run_articles (
            run_id TEXT NOT NULL,
            article_id TEXT NOT NULL,
            normalized_url TEXT NOT NULL,
            url TEXT NOT NULL,
            title TEXT NOT NULL,
            source_name TEXT NOT NULL,
            category TEXT NOT NULL,
            published_ts INTEGER,
            fetched_at INTEGER NOT NULL,
            is_new INTEGER NOT NULL,
            in_report INTEGER NOT NULL,
            report_position INTEGER,
            rss_summary TEXT NOT NULL DEFAULT '',
            ai_summary TEXT NOT NULL DEFAULT '',
            content_hash TEXT NOT NULL,
            PRIMARY KEY (run_id, article_id)
        );
        """
    )
    conn.commit()
    conn.close()

    with ArchiveStore(str(path)) as store:
        assert store.schema_version() == 6
        assert store.count_rows("article_contents") == 0
        assert store.count_rows("article_enrichments") == 0
        assert store.count_rows("article_chunks") == 0


def test_archive_store_migrates_v2_to_v3(tmp_path):
    path = tmp_path / "assets.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT INTO meta(key, value) VALUES ('schema_version', '2');
        CREATE TABLE runs (
            run_id TEXT PRIMARY KEY,
            generated_at INTEGER NOT NULL,
            generated_at_iso TEXT NOT NULL,
            output_path TEXT NOT NULL,
            view TEXT NOT NULL,
            incremental_mode TEXT NOT NULL,
            article_count INTEGER NOT NULL,
            all_article_count INTEGER NOT NULL,
            new_article_count INTEGER NOT NULL
        );
        CREATE TABLE articles (
            article_id TEXT PRIMARY KEY,
            normalized_url TEXT NOT NULL UNIQUE,
            url TEXT NOT NULL,
            source_id TEXT NOT NULL,
            source_name TEXT NOT NULL,
            category TEXT NOT NULL,
            title TEXT NOT NULL,
            published_ts INTEGER,
            first_seen_at INTEGER NOT NULL,
            last_seen_at INTEGER NOT NULL,
            latest_fetched_at INTEGER NOT NULL,
            rss_summary TEXT NOT NULL DEFAULT '',
            ai_summary TEXT NOT NULL DEFAULT '',
            content_hash TEXT NOT NULL,
            last_run_id TEXT,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        );
        CREATE TABLE run_articles (
            run_id TEXT NOT NULL,
            article_id TEXT NOT NULL,
            normalized_url TEXT NOT NULL,
            url TEXT NOT NULL,
            title TEXT NOT NULL,
            source_name TEXT NOT NULL,
            category TEXT NOT NULL,
            published_ts INTEGER,
            fetched_at INTEGER NOT NULL,
            is_new INTEGER NOT NULL,
            in_report INTEGER NOT NULL,
            report_position INTEGER,
            rss_summary TEXT NOT NULL DEFAULT '',
            ai_summary TEXT NOT NULL DEFAULT '',
            content_hash TEXT NOT NULL,
            PRIMARY KEY (run_id, article_id)
        );
        CREATE TABLE article_contents (
            article_id TEXT PRIMARY KEY,
            content_status TEXT NOT NULL DEFAULT 'not_fetched',
            content_source TEXT NOT NULL DEFAULT '',
            clean_text TEXT NOT NULL DEFAULT '',
            raw_html TEXT NOT NULL DEFAULT '',
            content_error TEXT NOT NULL DEFAULT '',
            content_http_status INTEGER,
            content_fetched_at INTEGER,
            content_final_url TEXT NOT NULL DEFAULT '',
            updated_at INTEGER NOT NULL
        );
        """
    )
    conn.commit()
    conn.close()

    with ArchiveStore(str(path)) as store:
        assert store.schema_version() == 6
        assert store.count_rows("article_contents") == 0
        assert store.count_rows("article_enrichments") == 0
        assert store.count_rows("article_chunks") == 0


def test_archive_store_migrates_v3_to_v4_and_backfills_chunks(tmp_path):
    path = tmp_path / "assets.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT INTO meta(key, value) VALUES ('schema_version', '3');
        CREATE TABLE runs (
            run_id TEXT PRIMARY KEY,
            generated_at INTEGER NOT NULL,
            generated_at_iso TEXT NOT NULL,
            output_path TEXT NOT NULL,
            view TEXT NOT NULL,
            incremental_mode TEXT NOT NULL,
            article_count INTEGER NOT NULL,
            all_article_count INTEGER NOT NULL,
            new_article_count INTEGER NOT NULL
        );
        CREATE TABLE articles (
            article_id TEXT PRIMARY KEY,
            normalized_url TEXT NOT NULL UNIQUE,
            url TEXT NOT NULL,
            source_id TEXT NOT NULL,
            source_name TEXT NOT NULL,
            category TEXT NOT NULL,
            title TEXT NOT NULL,
            published_ts INTEGER,
            first_seen_at INTEGER NOT NULL,
            last_seen_at INTEGER NOT NULL,
            latest_fetched_at INTEGER NOT NULL,
            rss_summary TEXT NOT NULL DEFAULT '',
            ai_summary TEXT NOT NULL DEFAULT '',
            content_hash TEXT NOT NULL,
            last_run_id TEXT,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        );
        CREATE TABLE run_articles (
            run_id TEXT NOT NULL,
            article_id TEXT NOT NULL,
            normalized_url TEXT NOT NULL,
            url TEXT NOT NULL,
            title TEXT NOT NULL,
            source_name TEXT NOT NULL,
            category TEXT NOT NULL,
            published_ts INTEGER,
            fetched_at INTEGER NOT NULL,
            is_new INTEGER NOT NULL,
            in_report INTEGER NOT NULL,
            report_position INTEGER,
            rss_summary TEXT NOT NULL DEFAULT '',
            ai_summary TEXT NOT NULL DEFAULT '',
            content_hash TEXT NOT NULL,
            PRIMARY KEY (run_id, article_id)
        );
        CREATE TABLE article_contents (
            article_id TEXT PRIMARY KEY,
            content_status TEXT NOT NULL DEFAULT 'not_fetched',
            content_source TEXT NOT NULL DEFAULT '',
            clean_text TEXT NOT NULL DEFAULT '',
            raw_html TEXT NOT NULL DEFAULT '',
            content_error TEXT NOT NULL DEFAULT '',
            content_http_status INTEGER,
            content_fetched_at INTEGER,
            content_final_url TEXT NOT NULL DEFAULT '',
            updated_at INTEGER NOT NULL
        );
        CREATE TABLE article_enrichments (
            article_id TEXT PRIMARY KEY,
            one_line_summary TEXT NOT NULL DEFAULT '',
            key_points_json TEXT NOT NULL DEFAULT '[]',
            why_it_matters TEXT NOT NULL DEFAULT '',
            recommended_for_json TEXT NOT NULL DEFAULT '[]',
            tags_json TEXT NOT NULL DEFAULT '[]',
            topic TEXT NOT NULL DEFAULT '',
            enrichment_status TEXT NOT NULL DEFAULT 'not_enriched',
            enrichment_error TEXT NOT NULL DEFAULT '',
            updated_at INTEGER NOT NULL
        );
        """
    )
    article = _article(
        title="Agent Memory Systems",
        url="https://example.com/memory",
        source_name="OpenAI News",
        rss_summary="memory agents summary",
        fetched_at=1744329600,
    )
    conn.execute(
        """
        INSERT INTO articles(
            article_id, normalized_url, url, source_id, source_name, category, title,
            published_ts, first_seen_at, last_seen_at, latest_fetched_at,
            rss_summary, ai_summary, content_hash, last_run_id, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            _build_article_id(_normalize_url(article.url)),
            _normalize_url(article.url),
            article.url,
            article.source_id,
            article.source_name,
            article.category,
            article.title,
            article.published_ts,
            1744329600,
            1744329600,
            1744329600,
            article.rss_summary,
            article.ai_summary,
            _build_content_hash(article),
            None,
            1744329600,
            1744329600,
        ),
    )
    conn.execute(
        """
        INSERT INTO article_contents(
            article_id, content_status, content_source, clean_text, raw_html,
            content_error, content_http_status, content_fetched_at, content_final_url, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            _build_article_id(_normalize_url(article.url)),
            "fetched",
            "html_article",
            "This article describes memory layers for agent workflows.",
            "",
            "",
            200,
            1744329600,
            article.url,
            1744329600,
        ),
    )
    conn.execute(
        """
        INSERT INTO article_enrichments(
            article_id, one_line_summary, key_points_json, why_it_matters,
            recommended_for_json, tags_json, topic, enrichment_status, enrichment_error, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            _build_article_id(_normalize_url(article.url)),
            "Memory agents summary",
            json.dumps(["point a"]),
            "Useful for long-running agents",
            json.dumps(["engineers"]),
            json.dumps(["agent", "memory"]),
            "智能体",
            "enriched",
            "",
            1744329600,
        ),
    )
    conn.commit()
    conn.close()

    with ArchiveStore(str(path)) as store:
        assert store.schema_version() == 6
        assert store.count_rows("article_chunks") >= 1
        chunks = store.retrieve_chunks(question="memory")
        assert chunks
        assert chunks[0]["url"] == article.url


def test_archive_store_migrates_v4_to_v5(tmp_path):
    path = tmp_path / "assets.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT INTO meta(key, value) VALUES ('schema_version', '4');
        CREATE TABLE runs (
            run_id TEXT PRIMARY KEY,
            generated_at INTEGER NOT NULL,
            generated_at_iso TEXT NOT NULL,
            output_path TEXT NOT NULL,
            view TEXT NOT NULL,
            incremental_mode TEXT NOT NULL,
            article_count INTEGER NOT NULL,
            all_article_count INTEGER NOT NULL,
            new_article_count INTEGER NOT NULL
        );
        CREATE TABLE articles (
            article_id TEXT PRIMARY KEY,
            normalized_url TEXT NOT NULL UNIQUE,
            url TEXT NOT NULL,
            source_id TEXT NOT NULL,
            source_name TEXT NOT NULL,
            category TEXT NOT NULL,
            title TEXT NOT NULL,
            published_ts INTEGER,
            first_seen_at INTEGER NOT NULL,
            last_seen_at INTEGER NOT NULL,
            latest_fetched_at INTEGER NOT NULL,
            rss_summary TEXT NOT NULL DEFAULT '',
            ai_summary TEXT NOT NULL DEFAULT '',
            content_hash TEXT NOT NULL,
            last_run_id TEXT,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        );
        CREATE TABLE run_articles (
            run_id TEXT NOT NULL,
            article_id TEXT NOT NULL,
            normalized_url TEXT NOT NULL,
            url TEXT NOT NULL,
            title TEXT NOT NULL,
            source_name TEXT NOT NULL,
            category TEXT NOT NULL,
            published_ts INTEGER,
            fetched_at INTEGER NOT NULL,
            is_new INTEGER NOT NULL,
            in_report INTEGER NOT NULL,
            report_position INTEGER,
            rss_summary TEXT NOT NULL DEFAULT '',
            ai_summary TEXT NOT NULL DEFAULT '',
            content_hash TEXT NOT NULL,
            PRIMARY KEY (run_id, article_id)
        );
        CREATE TABLE article_contents (
            article_id TEXT PRIMARY KEY,
            content_status TEXT NOT NULL DEFAULT 'not_fetched',
            content_source TEXT NOT NULL DEFAULT '',
            clean_text TEXT NOT NULL DEFAULT '',
            raw_html TEXT NOT NULL DEFAULT '',
            content_error TEXT NOT NULL DEFAULT '',
            content_http_status INTEGER,
            content_fetched_at INTEGER,
            content_final_url TEXT NOT NULL DEFAULT '',
            updated_at INTEGER NOT NULL
        );
        CREATE TABLE article_enrichments (
            article_id TEXT PRIMARY KEY,
            one_line_summary TEXT NOT NULL DEFAULT '',
            key_points_json TEXT NOT NULL DEFAULT '[]',
            why_it_matters TEXT NOT NULL DEFAULT '',
            recommended_for_json TEXT NOT NULL DEFAULT '[]',
            tags_json TEXT NOT NULL DEFAULT '[]',
            topic TEXT NOT NULL DEFAULT '',
            enrichment_status TEXT NOT NULL DEFAULT 'not_enriched',
            enrichment_error TEXT NOT NULL DEFAULT '',
            updated_at INTEGER NOT NULL
        );
        CREATE TABLE article_chunks (
            chunk_id TEXT PRIMARY KEY,
            article_id TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            source_kind TEXT NOT NULL DEFAULT '',
            text TEXT NOT NULL DEFAULT '',
            embedding_json TEXT NOT NULL DEFAULT '[]',
            updated_at INTEGER NOT NULL
        );
        """
    )
    conn.commit()
    conn.close()

    with ArchiveStore(str(path)) as store:
        assert store.schema_version() == 6
        assert store.count_rows("article_relevances") == 0
        assert store.count_rows("deliveries") == 0
        assert store.count_rows("feedback") == 0


def test_schema_version_mismatch_raises(tmp_path):
    path = tmp_path / "assets.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    conn.execute("INSERT INTO meta(key, value) VALUES ('schema_version', '999')")
    conn.commit()
    conn.close()

    with pytest.raises(ValueError):
        ArchiveStore(str(path))
