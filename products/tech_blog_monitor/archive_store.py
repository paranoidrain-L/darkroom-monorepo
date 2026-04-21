# -*- coding: utf-8 -*-
"""
Tech Blog Monitor — Phase 1 历史资产存储层

使用 sqlite 维护可检索的历史文章资产：
- runs: 每次执行的批次信息
- articles: 去重后的文章主记录
- run_articles: 某次执行中观测到的文章快照
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import SplitResult, urlsplit, urlunsplit
from uuid import uuid4

from products.tech_blog_monitor.chunking import build_chunks_for_article
from products.tech_blog_monitor.fetcher import Article
from products.tech_blog_monitor.retrieval import build_fake_embedding
from products.tech_blog_monitor.state import ArticleStateStore

_SCHEMA_VERSION = 6


def _normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    normalized = SplitResult(
        scheme=parts.scheme.lower(),
        netloc=parts.netloc.lower(),
        path=parts.path or "/",
        query=parts.query,
        fragment="",
    )
    return urlunsplit(normalized)


def _build_content_hash(article: Article) -> str:
    payload = {
        "title": article.title,
        "source_name": article.source_name,
        "published_ts": article.published_ts,
        "rss_summary": article.rss_summary,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _build_article_id(normalized_url: str) -> str:
    return hashlib.sha256(normalized_url.encode("utf-8")).hexdigest()


def _article_from_payload_item(item: object, default_fetched_at: int) -> Optional[Article]:
    if not isinstance(item, dict):
        return None

    url = item.get("url")
    title = item.get("title")
    source_name = item.get("source_name")
    category = item.get("category")
    source_id = item.get("source_id")
    fetched_at = item.get("fetched_at")
    if not all(isinstance(v, str) and v for v in (url, title, source_name, category, source_id)):
        return None
    if not isinstance(fetched_at, int):
        fetched_at = default_fetched_at

    return Article(
        title=title,
        url=url,
        source_name=source_name,
        source_type=item.get("source_type", "rss")
        if isinstance(item.get("source_type"), str)
        else "rss",
        category=category,
        source_id=source_id,
        rss_summary=item.get("rss_summary", "") if isinstance(item.get("rss_summary"), str) else "",
        published=None,
        published_ts=item.get("published_ts") if isinstance(item.get("published_ts"), int) else None,
        fetched_at=fetched_at,
        ai_summary=item.get("ai_summary", "") if isinstance(item.get("ai_summary"), str) else "",
        content_status=item.get("content_status", "not_fetched")
        if isinstance(item.get("content_status"), str)
        else "not_fetched",
        content_source=item.get("content_source", "") if isinstance(item.get("content_source"), str) else "",
        raw_html=item.get("raw_html", "") if isinstance(item.get("raw_html"), str) else "",
        clean_text=item.get("clean_text", "") if isinstance(item.get("clean_text"), str) else "",
        content_error=item.get("content_error", "") if isinstance(item.get("content_error"), str) else "",
        content_http_status=item.get("content_http_status")
        if isinstance(item.get("content_http_status"), int)
        else None,
        content_fetched_at=item.get("content_fetched_at")
        if isinstance(item.get("content_fetched_at"), int)
        else None,
        content_final_url=item.get("content_final_url", "")
        if isinstance(item.get("content_final_url"), str)
        else "",
        one_line_summary=item.get("one_line_summary", "")
        if isinstance(item.get("one_line_summary"), str)
        else "",
        key_points=[
            entry.strip()
            for entry in item.get("key_points", [])
            if isinstance(entry, str) and entry.strip()
        ]
        if isinstance(item.get("key_points"), list)
        else [],
        why_it_matters=item.get("why_it_matters", "")
        if isinstance(item.get("why_it_matters"), str)
        else "",
        recommended_for=[
            entry.strip()
            for entry in item.get("recommended_for", [])
            if isinstance(entry, str) and entry.strip()
        ]
        if isinstance(item.get("recommended_for"), list)
        else [],
        tags=[
            entry.strip()
            for entry in item.get("tags", [])
            if isinstance(entry, str) and entry.strip()
        ]
        if isinstance(item.get("tags"), list)
        else [],
        topic=item.get("topic", "") if isinstance(item.get("topic"), str) else "",
        enrichment_status=item.get("enrichment_status", "not_enriched")
        if isinstance(item.get("enrichment_status"), str)
        else "not_enriched",
        enrichment_error=item.get("enrichment_error", "")
        if isinstance(item.get("enrichment_error"), str)
        else "",
        relevance_score=float(item.get("relevance_score", 0.0) or 0.0),
        relevance_level=item.get("relevance_level", "not_evaluated")
        if isinstance(item.get("relevance_level"), str)
        else "not_evaluated",
        relevance_reasons=[
            entry.strip()
            for entry in item.get("relevance_reasons", [])
            if isinstance(entry, str) and entry.strip()
        ]
        if isinstance(item.get("relevance_reasons"), list)
        else [],
        matched_signals=[
            entry for entry in item.get("matched_signals", [])
            if isinstance(entry, dict)
        ]
        if isinstance(item.get("matched_signals"), list)
        else [],
        dependency_match_score=float(item.get("dependency_match_score", 0.0) or 0.0),
        topic_match_score=float(item.get("topic_match_score", 0.0) or 0.0),
        source_priority_score=float(item.get("source_priority_score", 0.0) or 0.0),
    )


class ArchiveStore:
    """Tech Blog 历史资产 sqlite 存储。"""

    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path))
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "ArchiveStore":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _init_schema(self) -> None:
        with self._conn:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS runs (
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

                CREATE TABLE IF NOT EXISTS articles (
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

                CREATE TABLE IF NOT EXISTS run_articles (
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
                    PRIMARY KEY (run_id, article_id),
                    FOREIGN KEY (run_id) REFERENCES runs(run_id),
                    FOREIGN KEY (article_id) REFERENCES articles(article_id)
                );

                CREATE INDEX IF NOT EXISTS idx_articles_source_name ON articles(source_name);
                CREATE INDEX IF NOT EXISTS idx_articles_category ON articles(category);
                CREATE INDEX IF NOT EXISTS idx_articles_published_ts ON articles(published_ts);
                CREATE INDEX IF NOT EXISTS idx_run_articles_run_id ON run_articles(run_id);
                CREATE INDEX IF NOT EXISTS idx_run_articles_report_position ON run_articles(run_id, report_position);
                """
            )

            row = self._conn.execute(
                "SELECT value FROM meta WHERE key = 'schema_version'"
            ).fetchone()
            if row is None:
                self._conn.execute(
                    "INSERT INTO meta(key, value) VALUES('schema_version', ?)",
                    (str(_SCHEMA_VERSION),),
                )
            else:
                current_version = int(row["value"])
                if current_version == 1:
                    self._migrate_v1_to_v2()
                    current_version = 2
                if current_version == 2:
                    self._migrate_v2_to_v3()
                    current_version = 3
                if current_version == 3:
                    self._migrate_v3_to_v4()
                    current_version = 4
                if current_version == 4:
                    self._migrate_v4_to_v5()
                    current_version = 5
                if current_version == 5:
                    self._migrate_v5_to_v6()
                    current_version = 6
                if current_version != _SCHEMA_VERSION:
                    raise ValueError(
                        f"ArchiveStore schema_version={row['value']} 与当前版本 {_SCHEMA_VERSION} 不兼容"
                    )

            self._ensure_content_schema()
            self._ensure_enrichment_schema()
            self._ensure_chunk_schema()
            self._ensure_delivery_schema()
            self._ensure_relevance_schema()
            self._backfill_missing_chunks()

    def _ensure_content_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS article_contents (
                article_id TEXT PRIMARY KEY,
                content_status TEXT NOT NULL DEFAULT 'not_fetched',
                content_source TEXT NOT NULL DEFAULT '',
                clean_text TEXT NOT NULL DEFAULT '',
                raw_html TEXT NOT NULL DEFAULT '',
                content_error TEXT NOT NULL DEFAULT '',
                content_http_status INTEGER,
                content_fetched_at INTEGER,
                content_final_url TEXT NOT NULL DEFAULT '',
                updated_at INTEGER NOT NULL,
                FOREIGN KEY (article_id) REFERENCES articles(article_id)
            );
            """
        )

    def _ensure_enrichment_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS article_enrichments (
                article_id TEXT PRIMARY KEY,
                one_line_summary TEXT NOT NULL DEFAULT '',
                key_points_json TEXT NOT NULL DEFAULT '[]',
                why_it_matters TEXT NOT NULL DEFAULT '',
                recommended_for_json TEXT NOT NULL DEFAULT '[]',
                tags_json TEXT NOT NULL DEFAULT '[]',
                topic TEXT NOT NULL DEFAULT '',
                enrichment_status TEXT NOT NULL DEFAULT 'not_enriched',
                enrichment_error TEXT NOT NULL DEFAULT '',
                updated_at INTEGER NOT NULL,
                FOREIGN KEY (article_id) REFERENCES articles(article_id)
            );
            """
        )

    def _migrate_v1_to_v2(self) -> None:
        self._ensure_content_schema()
        self._conn.execute(
            "UPDATE meta SET value = ? WHERE key = 'schema_version'",
            ("2",),
        )

    def _migrate_v2_to_v3(self) -> None:
        self._ensure_content_schema()
        self._ensure_enrichment_schema()
        self._conn.execute(
            "UPDATE meta SET value = ? WHERE key = 'schema_version'",
            ("3",),
        )

    def _ensure_chunk_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS article_chunks (
                chunk_id TEXT PRIMARY KEY,
                article_id TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                source_kind TEXT NOT NULL DEFAULT '',
                text TEXT NOT NULL DEFAULT '',
                embedding_json TEXT NOT NULL DEFAULT '[]',
                updated_at INTEGER NOT NULL,
                UNIQUE(article_id, chunk_index),
                FOREIGN KEY (article_id) REFERENCES articles(article_id)
            );

            CREATE INDEX IF NOT EXISTS idx_article_chunks_article_id
            ON article_chunks(article_id);
            """
        )

    def _migrate_v3_to_v4(self) -> None:
        self._ensure_chunk_schema()
        self._conn.execute(
            "UPDATE meta SET value = ? WHERE key = 'schema_version'",
            ("4",),
        )

    def _ensure_delivery_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS deliveries (
                delivery_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                role TEXT NOT NULL,
                cadence TEXT NOT NULL,
                dedupe_key TEXT NOT NULL UNIQUE,
                payload_json TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL,
                attempt_count INTEGER NOT NULL DEFAULT 0,
                last_error TEXT NOT NULL DEFAULT '',
                delivered_at INTEGER,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                FOREIGN KEY (run_id) REFERENCES runs(run_id)
            );

            CREATE INDEX IF NOT EXISTS idx_deliveries_run_id
            ON deliveries(run_id);

            CREATE INDEX IF NOT EXISTS idx_deliveries_status
            ON deliveries(status);

            CREATE TABLE IF NOT EXISTS feedback (
                feedback_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                role TEXT NOT NULL,
                feedback_type TEXT NOT NULL,
                feedback_text TEXT NOT NULL DEFAULT '',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at INTEGER NOT NULL,
                FOREIGN KEY (run_id) REFERENCES runs(run_id)
            );

            CREATE INDEX IF NOT EXISTS idx_feedback_run_id
            ON feedback(run_id);
            """
        )

    def _migrate_v4_to_v5(self) -> None:
        self._ensure_delivery_schema()
        self._conn.execute(
            "UPDATE meta SET value = ? WHERE key = 'schema_version'",
            ("5",),
        )

    def _ensure_relevance_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS article_relevances (
                article_id TEXT PRIMARY KEY,
                relevance_score REAL NOT NULL DEFAULT 0,
                relevance_level TEXT NOT NULL DEFAULT 'not_evaluated',
                relevance_reasons_json TEXT NOT NULL DEFAULT '[]',
                matched_signals_json TEXT NOT NULL DEFAULT '[]',
                dependency_match_score REAL NOT NULL DEFAULT 0,
                topic_match_score REAL NOT NULL DEFAULT 0,
                source_priority_score REAL NOT NULL DEFAULT 0,
                updated_at INTEGER NOT NULL,
                FOREIGN KEY (article_id) REFERENCES articles(article_id)
            );
            """
        )

    def _migrate_v5_to_v6(self) -> None:
        self._ensure_relevance_schema()
        self._conn.execute(
            "UPDATE meta SET value = ? WHERE key = 'schema_version'",
            (str(_SCHEMA_VERSION),),
        )

    def schema_version(self) -> int:
        row = self._conn.execute(
            "SELECT value FROM meta WHERE key = 'schema_version'"
        ).fetchone()
        return int(row["value"]) if row is not None else _SCHEMA_VERSION

    def _upsert_content(self, article_id: str, article: Article, observed_at: int) -> None:
        self._conn.execute(
            """
            INSERT INTO article_contents(
                article_id, content_status, content_source, clean_text, raw_html,
                content_error, content_http_status, content_fetched_at, content_final_url, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(article_id) DO UPDATE SET
                content_status = excluded.content_status,
                content_source = excluded.content_source,
                clean_text = excluded.clean_text,
                raw_html = excluded.raw_html,
                content_error = excluded.content_error,
                content_http_status = excluded.content_http_status,
                content_fetched_at = excluded.content_fetched_at,
                content_final_url = excluded.content_final_url,
                updated_at = excluded.updated_at
            """,
            (
                article_id,
                article.content_status,
                article.content_source,
                article.clean_text,
                article.raw_html,
                article.content_error,
                article.content_http_status,
                article.content_fetched_at,
                article.content_final_url,
                observed_at,
            ),
        )

    def _upsert_enrichment(self, article_id: str, article: Article, observed_at: int) -> None:
        self._conn.execute(
            """
            INSERT INTO article_enrichments(
                article_id, one_line_summary, key_points_json, why_it_matters,
                recommended_for_json, tags_json, topic, enrichment_status,
                enrichment_error, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(article_id) DO UPDATE SET
                one_line_summary = excluded.one_line_summary,
                key_points_json = excluded.key_points_json,
                why_it_matters = excluded.why_it_matters,
                recommended_for_json = excluded.recommended_for_json,
                tags_json = excluded.tags_json,
                topic = excluded.topic,
                enrichment_status = excluded.enrichment_status,
                enrichment_error = excluded.enrichment_error,
                updated_at = excluded.updated_at
            """,
            (
                article_id,
                article.one_line_summary,
                json.dumps(article.key_points, ensure_ascii=False),
                article.why_it_matters,
                json.dumps(article.recommended_for, ensure_ascii=False),
                json.dumps(article.tags, ensure_ascii=False),
                article.topic,
                article.enrichment_status,
                article.enrichment_error,
                observed_at,
            ),
        )

    def _upsert_relevance(self, article_id: str, article: Article, observed_at: int) -> None:
        self._conn.execute(
            """
            INSERT INTO article_relevances(
                article_id, relevance_score, relevance_level, relevance_reasons_json,
                matched_signals_json, dependency_match_score, topic_match_score,
                source_priority_score, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(article_id) DO UPDATE SET
                relevance_score = excluded.relevance_score,
                relevance_level = excluded.relevance_level,
                relevance_reasons_json = excluded.relevance_reasons_json,
                matched_signals_json = excluded.matched_signals_json,
                dependency_match_score = excluded.dependency_match_score,
                topic_match_score = excluded.topic_match_score,
                source_priority_score = excluded.source_priority_score,
                updated_at = excluded.updated_at
            """,
            (
                article_id,
                article.relevance_score,
                article.relevance_level,
                json.dumps(article.relevance_reasons, ensure_ascii=False),
                json.dumps(article.matched_signals, ensure_ascii=False),
                article.dependency_match_score,
                article.topic_match_score,
                article.source_priority_score,
                observed_at,
            ),
        )

    def _upsert_chunks(self, article_id: str, article: Article, observed_at: int) -> None:
        chunks = build_chunks_for_article(article)
        self._conn.execute(
            "DELETE FROM article_chunks WHERE article_id = ?",
            (article_id,),
        )
        for chunk in chunks:
            chunk_id = f"{article_id}:{chunk.chunk_index}"
            self._conn.execute(
                """
                INSERT INTO article_chunks(
                    chunk_id, article_id, chunk_index, source_kind, text, embedding_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chunk_id,
                    article_id,
                    chunk.chunk_index,
                    chunk.source_kind,
                    chunk.text,
                    json.dumps(build_fake_embedding(chunk.text), ensure_ascii=False),
                    observed_at,
                ),
            )

    def _upsert_article(self, article: Article, observed_at: int, run_id: str) -> str:
        normalized_url = _normalize_url(article.url)
        article_id = _build_article_id(normalized_url)
        content_hash = _build_content_hash(article)
        self._conn.execute(
            """
            INSERT INTO articles (
                article_id, normalized_url, url, source_id, source_name, category, title,
                published_ts, first_seen_at, last_seen_at, latest_fetched_at,
                rss_summary, ai_summary, content_hash, last_run_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(normalized_url) DO UPDATE SET
                url = excluded.url,
                source_id = excluded.source_id,
                source_name = excluded.source_name,
                category = excluded.category,
                title = excluded.title,
                published_ts = COALESCE(excluded.published_ts, articles.published_ts),
                first_seen_at = MIN(articles.first_seen_at, excluded.first_seen_at),
                last_seen_at = MAX(articles.last_seen_at, excluded.last_seen_at),
                latest_fetched_at = MAX(articles.latest_fetched_at, excluded.latest_fetched_at),
                rss_summary = excluded.rss_summary,
                ai_summary = CASE
                    WHEN excluded.ai_summary != '' THEN excluded.ai_summary
                    ELSE articles.ai_summary
                END,
                content_hash = excluded.content_hash,
                last_run_id = excluded.last_run_id,
                updated_at = excluded.updated_at
            """,
            (
                article_id,
                normalized_url,
                article.url,
                article.source_id,
                article.source_name,
                article.category,
                article.title,
                article.published_ts,
                observed_at,
                observed_at,
                article.fetched_at,
                article.rss_summary,
                article.ai_summary,
                content_hash,
                run_id,
                observed_at,
                observed_at,
            ),
        )
        return article_id

    def record_run(
        self,
        *,
        generated_at: int,
        generated_at_iso: str,
        output_path: str,
        view: str,
        incremental_mode: str,
        all_articles: List[Article],
        report_articles: List[Article],
        new_urls: set[str],
    ) -> str:
        run_id = f"run_{generated_at_iso.replace(':', '').replace('-', '')}_{uuid4().hex[:8]}"
        report_positions = {article.url: index for index, article in enumerate(report_articles)}

        with self._conn:
            self._conn.execute(
                """
                INSERT INTO runs(
                    run_id, generated_at, generated_at_iso, output_path, view,
                    incremental_mode, article_count, all_article_count, new_article_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    generated_at,
                    generated_at_iso,
                    output_path,
                    view,
                    incremental_mode,
                    len(report_articles),
                    len(all_articles),
                    sum(1 for article in all_articles if article.url in new_urls),
                ),
            )

            for article in all_articles:
                article_id = self._upsert_article(article, generated_at, run_id)
                self._upsert_content(article_id, article, generated_at)
                self._upsert_enrichment(article_id, article, generated_at)
                self._upsert_relevance(article_id, article, generated_at)
                self._upsert_chunks(article_id, article, generated_at)
                normalized_url = _normalize_url(article.url)
                self._conn.execute(
                    """
                    INSERT OR REPLACE INTO run_articles(
                        run_id, article_id, normalized_url, url, title, source_name,
                        category, published_ts, fetched_at, is_new, in_report,
                        report_position, rss_summary, ai_summary, content_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        article_id,
                        normalized_url,
                        article.url,
                        article.title,
                        article.source_name,
                        article.category,
                        article.published_ts,
                        article.fetched_at,
                        1 if article.url in new_urls else 0,
                        1 if article.url in report_positions else 0,
                        report_positions.get(article.url),
                        article.rss_summary,
                        article.ai_summary,
                        _build_content_hash(article),
                    ),
                )

        return run_id

    def import_state_file(self, path: str) -> int:
        store = ArticleStateStore(path)
        imported = 0
        with self._conn:
            for url, record in store.items():
                normalized_url = _normalize_url(url)
                article_id = _build_article_id(normalized_url)
                observed_at = record.last_seen_at
                self._conn.execute(
                    """
                    INSERT INTO articles(
                        article_id, normalized_url, url, source_id, source_name, category, title,
                        published_ts, first_seen_at, last_seen_at, latest_fetched_at,
                        rss_summary, ai_summary, content_hash, last_run_id, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(normalized_url) DO UPDATE SET
                        source_id = excluded.source_id,
                        source_name = excluded.source_name,
                        category = excluded.category,
                        title = CASE WHEN excluded.title != '' THEN excluded.title ELSE articles.title END,
                        published_ts = COALESCE(excluded.published_ts, articles.published_ts),
                        first_seen_at = MIN(articles.first_seen_at, excluded.first_seen_at),
                        last_seen_at = MAX(articles.last_seen_at, excluded.last_seen_at),
                        latest_fetched_at = MAX(articles.latest_fetched_at, excluded.latest_fetched_at),
                        updated_at = excluded.updated_at
                    """,
                    (
                        article_id,
                        normalized_url,
                        url,
                        f"{record.source_name}::{url}" if record.source_name else f"legacy::{url}",
                        record.source_name or "",
                        record.category or "",
                        record.title or "",
                        record.published_ts,
                        record.first_seen_at,
                        record.last_seen_at,
                        observed_at,
                        "",
                        "",
                        hashlib.sha256(url.encode("utf-8")).hexdigest(),
                        None,
                        record.first_seen_at,
                        observed_at,
                    ),
                )
                imported += 1
        return imported

    def ingest_archive_payload(self, payload: Dict[str, Any], output_path: str = "") -> str:
        generated_at = payload.get("generated_at")
        if not isinstance(generated_at, int):
            raise ValueError("archive payload 缺少合法 generated_at")
        generated_at_iso = payload.get("generated_at_iso")
        if not isinstance(generated_at_iso, str) or not generated_at_iso:
            generated_at_iso = f"{generated_at}"

        raw_all_articles = payload.get("all_articles")
        raw_report_articles = payload.get("articles")
        if not isinstance(raw_all_articles, list):
            raw_all_articles = raw_report_articles if isinstance(raw_report_articles, list) else []
        if not isinstance(raw_report_articles, list):
            raw_report_articles = raw_all_articles

        all_articles = [
            article
            for item in raw_all_articles
            if (article := _article_from_payload_item(item, generated_at)) is not None
        ]
        report_articles = [
            article
            for item in raw_report_articles
            if (article := _article_from_payload_item(item, generated_at)) is not None
        ]

        return self.record_run(
            generated_at=generated_at,
            generated_at_iso=generated_at_iso,
            output_path=output_path,
            view=payload.get("view", "by_category") if isinstance(payload.get("view"), str) else "by_category",
            incremental_mode=(
                payload.get("incremental_mode", "split")
                if isinstance(payload.get("incremental_mode"), str)
                else "split"
            ),
            all_articles=all_articles,
            report_articles=report_articles,
            new_urls={
                item["url"]
                for item in payload.get("new_articles", [])
                if isinstance(item, dict) and isinstance(item.get("url"), str)
            },
        )

    def get_article_by_url(self, url: str) -> Optional[Dict[str, Any]]:
        row = self._conn.execute(
            """
            SELECT
                articles.*,
                article_contents.content_status,
                article_contents.content_source,
                article_contents.clean_text,
                article_contents.raw_html,
                article_contents.content_error,
                article_contents.content_http_status,
                article_contents.content_fetched_at,
                article_contents.content_final_url,
                article_enrichments.one_line_summary,
                article_enrichments.key_points_json,
                article_enrichments.why_it_matters,
                article_enrichments.recommended_for_json,
                article_enrichments.tags_json,
                article_enrichments.topic,
                article_enrichments.enrichment_status,
                article_enrichments.enrichment_error,
                article_relevances.relevance_score,
                article_relevances.relevance_level,
                article_relevances.relevance_reasons_json,
                article_relevances.matched_signals_json,
                article_relevances.dependency_match_score,
                article_relevances.topic_match_score,
                article_relevances.source_priority_score
            FROM articles
            LEFT JOIN article_contents ON article_contents.article_id = articles.article_id
            LEFT JOIN article_enrichments ON article_enrichments.article_id = articles.article_id
            LEFT JOIN article_relevances ON article_relevances.article_id = articles.article_id
            WHERE articles.normalized_url = ?
            """,
            (_normalize_url(url),),
        ).fetchone()
        return self._decode_article_row(row)

    def list_recent_articles(self, limit: int = 20) -> List[Dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT
                articles.*,
                article_contents.content_status,
                article_contents.content_source,
                article_contents.clean_text,
                article_contents.content_error,
                article_contents.content_http_status,
                article_contents.content_fetched_at,
                article_contents.content_final_url,
                article_enrichments.one_line_summary,
                article_enrichments.key_points_json,
                article_enrichments.why_it_matters,
                article_enrichments.recommended_for_json,
                article_enrichments.tags_json,
                article_enrichments.topic,
                article_enrichments.enrichment_status,
                article_enrichments.enrichment_error,
                article_relevances.relevance_score,
                article_relevances.relevance_level,
                article_relevances.relevance_reasons_json,
                article_relevances.matched_signals_json,
                article_relevances.dependency_match_score,
                article_relevances.topic_match_score,
                article_relevances.source_priority_score
            FROM articles
            LEFT JOIN article_contents ON article_contents.article_id = articles.article_id
            LEFT JOIN article_enrichments ON article_enrichments.article_id = articles.article_id
            LEFT JOIN article_relevances ON article_relevances.article_id = articles.article_id
            ORDER BY COALESCE(articles.published_ts, articles.last_seen_at) DESC, articles.updated_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [self._decode_article_row(row) for row in rows]

    def list_articles(
        self,
        *,
        source_name: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        clauses = []
        params: List[Any] = []
        if source_name:
            clauses.append("source_name = ?")
            params.append(source_name)
        if category:
            clauses.append("category = ?")
            params.append(category)

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._conn.execute(
            f"""
            SELECT
                articles.*,
                article_contents.content_status,
                article_contents.content_source,
                article_contents.clean_text,
                article_contents.content_error,
                article_contents.content_http_status,
                article_contents.content_fetched_at,
                article_contents.content_final_url,
                article_enrichments.one_line_summary,
                article_enrichments.key_points_json,
                article_enrichments.why_it_matters,
                article_enrichments.recommended_for_json,
                article_enrichments.tags_json,
                article_enrichments.topic,
                article_enrichments.enrichment_status,
                article_enrichments.enrichment_error,
                article_relevances.relevance_score,
                article_relevances.relevance_level,
                article_relevances.relevance_reasons_json,
                article_relevances.matched_signals_json,
                article_relevances.dependency_match_score,
                article_relevances.topic_match_score,
                article_relevances.source_priority_score
            FROM articles
            LEFT JOIN article_contents ON article_contents.article_id = articles.article_id
            LEFT JOIN article_enrichments ON article_enrichments.article_id = articles.article_id
            LEFT JOIN article_relevances ON article_relevances.article_id = articles.article_id
            {where_sql}
            ORDER BY COALESCE(articles.published_ts, articles.last_seen_at) DESC, articles.updated_at DESC
            LIMIT ?
            """,
            (*params, limit),
        ).fetchall()
        return [self._decode_article_row(row) for row in rows]

    def get_article(self, article_id: str) -> Optional[Dict[str, Any]]:
        row = self._conn.execute(
            """
            SELECT
                articles.*,
                article_contents.content_status,
                article_contents.content_source,
                article_contents.clean_text,
                article_contents.raw_html,
                article_contents.content_error,
                article_contents.content_http_status,
                article_contents.content_fetched_at,
                article_contents.content_final_url,
                article_enrichments.one_line_summary,
                article_enrichments.key_points_json,
                article_enrichments.why_it_matters,
                article_enrichments.recommended_for_json,
                article_enrichments.tags_json,
                article_enrichments.topic,
                article_enrichments.enrichment_status,
                article_enrichments.enrichment_error,
                article_relevances.relevance_score,
                article_relevances.relevance_level,
                article_relevances.relevance_reasons_json,
                article_relevances.matched_signals_json,
                article_relevances.dependency_match_score,
                article_relevances.topic_match_score,
                article_relevances.source_priority_score
            FROM articles
            LEFT JOIN article_contents ON article_contents.article_id = articles.article_id
            LEFT JOIN article_enrichments ON article_enrichments.article_id = articles.article_id
            LEFT JOIN article_relevances ON article_relevances.article_id = articles.article_id
            WHERE articles.article_id = ?
            """,
            (article_id,),
        ).fetchone()
        return self._decode_article_row(row)

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        row = self._conn.execute(
            "SELECT * FROM runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        return dict(row) if row is not None else None

    def list_runs(self, limit: int = 20, offset: int = 0) -> List[Dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT * FROM runs
            ORDER BY generated_at DESC, run_id DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()
        return [dict(row) for row in rows]

    def list_run_articles(self, run_id: str) -> List[Dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT * FROM run_articles
            WHERE run_id = ?
            ORDER BY
                CASE WHEN report_position IS NULL THEN 1 ELSE 0 END,
                report_position ASC,
                published_ts DESC
            """,
            (run_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def count_rows(self, table: str) -> int:
        row = self._conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
        return int(row["n"])

    def create_delivery(
        self,
        *,
        run_id: str,
        role: str,
        cadence: str,
        dedupe_key: str,
        payload: Dict[str, Any],
        created_at: int,
    ) -> Dict[str, Any]:
        delivery_id = f"delivery_{uuid4().hex[:12]}"
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO deliveries(
                    delivery_id, run_id, role, cadence, dedupe_key, payload_json,
                    status, attempt_count, last_error, delivered_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(dedupe_key) DO NOTHING
                """,
                (
                    delivery_id,
                    run_id,
                    role,
                    cadence,
                    dedupe_key,
                    json.dumps(payload, ensure_ascii=False),
                    "pending",
                    0,
                    "",
                    None,
                    created_at,
                    created_at,
                ),
            )
        row = self._conn.execute(
            "SELECT * FROM deliveries WHERE dedupe_key = ?",
            (dedupe_key,),
        ).fetchone()
        return self._decode_delivery_row(row)

    def list_deliveries(
        self,
        *,
        run_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        clauses: List[str] = []
        params: List[Any] = []
        if run_id:
            clauses.append("run_id = ?")
            params.append(run_id)
        if status:
            clauses.append("status = ?")
            params.append(status)
        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._conn.execute(
            f"""
            SELECT * FROM deliveries
            {where_sql}
            ORDER BY created_at ASC, delivery_id ASC
            """,
            params,
        ).fetchall()
        return [self._decode_delivery_row(row) for row in rows]

    def mark_delivery_attempt(
        self,
        delivery_id: str,
        *,
        status: str,
        error: str = "",
        delivered_at: Optional[int] = None,
        updated_at: int,
    ) -> None:
        with self._conn:
            self._conn.execute(
                """
                UPDATE deliveries
                SET
                    status = ?,
                    attempt_count = attempt_count + 1,
                    last_error = ?,
                    delivered_at = ?,
                    updated_at = ?
                WHERE delivery_id = ?
                """,
                (status, error, delivered_at, updated_at, delivery_id),
            )

    def add_feedback(
        self,
        *,
        run_id: str,
        role: str,
        feedback_type: str,
        feedback_text: str,
        metadata: Dict[str, Any],
        created_at: int,
    ) -> str:
        feedback_id = f"feedback_{uuid4().hex[:12]}"
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO feedback(
                    feedback_id, run_id, role, feedback_type, feedback_text, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    feedback_id,
                    run_id,
                    role,
                    feedback_type,
                    feedback_text,
                    json.dumps(metadata, ensure_ascii=False),
                    created_at,
                ),
            )
        return feedback_id

    def list_feedback(
        self,
        *,
        run_id: Optional[str] = None,
        role: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        clauses: List[str] = []
        params: List[Any] = []
        if run_id:
            clauses.append("run_id = ?")
            params.append(run_id)
        if role:
            clauses.append("role = ?")
            params.append(role)
        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._conn.execute(
            f"""
            SELECT * FROM feedback
            {where_sql}
            ORDER BY created_at ASC, feedback_id ASC
            """,
            params,
        ).fetchall()
        return [self._decode_feedback_row(row) for row in rows]

    def _backfill_missing_chunks(self) -> None:
        rows = self._conn.execute(
            """
            SELECT
                articles.article_id,
                articles.title,
                articles.url,
                articles.source_name,
                articles.category,
                articles.source_id,
                articles.rss_summary,
                articles.published_ts,
                articles.latest_fetched_at,
                article_contents.content_status,
                article_contents.content_source,
                article_contents.raw_html,
                article_contents.clean_text,
                article_contents.content_error,
                article_contents.content_http_status,
                article_contents.content_fetched_at,
                article_contents.content_final_url,
                article_enrichments.one_line_summary,
                article_enrichments.key_points_json,
                article_enrichments.why_it_matters,
                article_enrichments.recommended_for_json,
                article_enrichments.tags_json,
                article_enrichments.topic,
                article_enrichments.enrichment_status,
                article_enrichments.enrichment_error
            FROM articles
            LEFT JOIN article_contents ON article_contents.article_id = articles.article_id
            LEFT JOIN article_enrichments ON article_enrichments.article_id = articles.article_id
            WHERE NOT EXISTS (
                SELECT 1 FROM article_chunks
                WHERE article_chunks.article_id = articles.article_id
            )
            """
        ).fetchall()

        for row in rows:
            article = _article_from_payload_item(
                {
                    "title": row["title"],
                    "url": row["url"],
                    "source_name": row["source_name"],
                    "category": row["category"],
                    "source_id": row["source_id"],
                    "rss_summary": row["rss_summary"],
                    "published_ts": row["published_ts"],
                    "fetched_at": row["latest_fetched_at"],
                    "content_status": row["content_status"] or "not_fetched",
                    "content_source": row["content_source"] or "",
                    "raw_html": row["raw_html"] or "",
                    "clean_text": row["clean_text"] or "",
                    "content_error": row["content_error"] or "",
                    "content_http_status": row["content_http_status"],
                    "content_fetched_at": row["content_fetched_at"],
                    "content_final_url": row["content_final_url"] or "",
                    "one_line_summary": row["one_line_summary"] or "",
                    "key_points": json.loads(row["key_points_json"] or "[]"),
                    "why_it_matters": row["why_it_matters"] or "",
                    "recommended_for": json.loads(row["recommended_for_json"] or "[]"),
                    "tags": json.loads(row["tags_json"] or "[]"),
                    "topic": row["topic"] or "",
                    "enrichment_status": row["enrichment_status"] or "not_enriched",
                    "enrichment_error": row["enrichment_error"] or "",
                },
                row["latest_fetched_at"],
            )
            if article is None:
                continue
            self._upsert_chunks(row["article_id"], article, row["latest_fetched_at"])

    def retrieve_chunks(self, *, question: str, limit: int = 25) -> List[Dict[str, Any]]:
        like = f"%{question.strip().lower()}%"
        rows = self._conn.execute(
            """
            SELECT
                article_chunks.chunk_id,
                article_chunks.article_id,
                article_chunks.chunk_index,
                article_chunks.source_kind,
                article_chunks.text,
                article_chunks.embedding_json,
                articles.title,
                articles.url,
                articles.source_name,
                articles.category,
                articles.published_ts,
                article_enrichments.topic,
                article_enrichments.one_line_summary,
                article_enrichments.why_it_matters,
                article_enrichments.tags_json
            FROM article_chunks
            JOIN articles ON articles.article_id = article_chunks.article_id
            LEFT JOIN article_enrichments ON article_enrichments.article_id = articles.article_id
            WHERE
                ? = ''
                OR lower(article_chunks.text) LIKE ?
                OR lower(articles.title) LIKE ?
                OR lower(COALESCE(article_enrichments.topic, '')) LIKE ?
                OR lower(COALESCE(article_enrichments.one_line_summary, '')) LIKE ?
                OR lower(COALESCE(article_enrichments.why_it_matters, '')) LIKE ?
                OR lower(COALESCE(article_enrichments.tags_json, '')) LIKE ?
            ORDER BY
                COALESCE(articles.published_ts, articles.updated_at) DESC,
                article_chunks.chunk_index ASC
            LIMIT ?
            """,
            (question.strip().lower(), like, like, like, like, like, like, limit),
        ).fetchall()

        payloads: List[Dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["tags"] = json.loads(item.pop("tags_json", "[]") or "[]")
            item["embedding"] = json.loads(item.pop("embedding_json", "[]") or "[]")
            payloads.append(item)
        return payloads

    def search_articles(
        self,
        *,
        query: str = "",
        source_name: Optional[str] = None,
        category: Optional[str] = None,
        topic: Optional[str] = None,
        tag: Optional[str] = None,
        published_from_ts: Optional[int] = None,
        published_to_ts: Optional[int] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        clauses: List[str] = []
        params: List[Any] = []

        if source_name:
            clauses.append("articles.source_name = ?")
            params.append(source_name)
        if category:
            clauses.append("articles.category = ?")
            params.append(category)
        if topic:
            clauses.append("article_enrichments.topic = ?")
            params.append(topic)
        if tag:
            clauses.append("article_enrichments.tags_json LIKE ?")
            params.append(f'%"{tag}"%')
        if published_from_ts is not None:
            clauses.append("articles.published_ts >= ?")
            params.append(published_from_ts)
        if published_to_ts is not None:
            clauses.append("articles.published_ts <= ?")
            params.append(published_to_ts)

        search_clause = ""
        if query.strip():
            like = f"%{query.strip().lower()}%"
            search_clause = """
                (
                    lower(articles.title) LIKE ?
                    OR lower(articles.rss_summary) LIKE ?
                    OR lower(article_contents.clean_text) LIKE ?
                    OR lower(article_enrichments.one_line_summary) LIKE ?
                    OR lower(article_enrichments.why_it_matters) LIKE ?
                    OR lower(article_enrichments.tags_json) LIKE ?
                    OR lower(article_enrichments.topic) LIKE ?
                )
            """
            clauses.append(search_clause)
            params.extend([like, like, like, like, like, like, like])

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        order_sql = """
            ORDER BY
                (
                    CASE WHEN ? != '' AND lower(articles.title) LIKE ? THEN 30 ELSE 0 END
                    + CASE WHEN ? != '' AND lower(article_enrichments.topic) LIKE ? THEN 20 ELSE 0 END
                    + CASE WHEN ? != '' AND lower(article_enrichments.tags_json) LIKE ? THEN 15 ELSE 0 END
                    + CASE WHEN ? != '' AND lower(article_enrichments.one_line_summary) LIKE ? THEN 10 ELSE 0 END
                    + CASE WHEN ? != '' AND lower(article_contents.clean_text) LIKE ? THEN 5 ELSE 0 END
                ) DESC,
                COALESCE(articles.published_ts, articles.last_seen_at) DESC,
                articles.updated_at DESC
        """

        query_text = query.strip().lower()
        title_like = f"%{query_text}%"
        topic_like = f"%{query_text}%"
        tag_like = f"%{query_text}%"
        summary_like = f"%{query_text}%"
        clean_text_like = f"%{query_text}%"

        rows = self._conn.execute(
            f"""
            SELECT
                articles.*,
                article_contents.content_status,
                article_contents.content_source,
                article_contents.clean_text,
                article_contents.content_error,
                article_contents.content_http_status,
                article_contents.content_fetched_at,
                article_contents.content_final_url,
                article_enrichments.one_line_summary,
                article_enrichments.key_points_json,
                article_enrichments.why_it_matters,
                article_enrichments.recommended_for_json,
                article_enrichments.tags_json,
                article_enrichments.topic,
                article_enrichments.enrichment_status,
                article_enrichments.enrichment_error,
                article_relevances.relevance_score,
                article_relevances.relevance_level,
                article_relevances.relevance_reasons_json,
                article_relevances.matched_signals_json,
                article_relevances.dependency_match_score,
                article_relevances.topic_match_score,
                article_relevances.source_priority_score
            FROM articles
            LEFT JOIN article_contents ON article_contents.article_id = articles.article_id
            LEFT JOIN article_enrichments ON article_enrichments.article_id = articles.article_id
            LEFT JOIN article_relevances ON article_relevances.article_id = articles.article_id
            {where_sql}
            {order_sql}
            LIMIT ?
            """,
            (
                *params,
                query_text,
                title_like,
                query_text,
                topic_like,
                query_text,
                tag_like,
                query_text,
                summary_like,
                query_text,
                clean_text_like,
                limit,
            ),
        ).fetchall()
        return [self._decode_article_row(row) for row in rows]

    def _decode_article_row(self, row: Optional[sqlite3.Row]) -> Optional[Dict[str, Any]]:
        if row is None:
            return None
        data = dict(row)
        data["key_points"] = json.loads(data.pop("key_points_json", "[]") or "[]")
        data["recommended_for"] = json.loads(data.pop("recommended_for_json", "[]") or "[]")
        data["tags"] = json.loads(data.pop("tags_json", "[]") or "[]")
        data["relevance_reasons"] = json.loads(data.pop("relevance_reasons_json", "[]") or "[]")
        data["matched_signals"] = json.loads(data.pop("matched_signals_json", "[]") or "[]")
        data["relevance_score"] = float(data.get("relevance_score") or 0.0)
        data["dependency_match_score"] = float(data.get("dependency_match_score") or 0.0)
        data["topic_match_score"] = float(data.get("topic_match_score") or 0.0)
        data["source_priority_score"] = float(data.get("source_priority_score") or 0.0)
        data["relevance_level"] = data.get("relevance_level") or "not_evaluated"
        return data

    def _decode_delivery_row(self, row: Optional[sqlite3.Row]) -> Optional[Dict[str, Any]]:
        if row is None:
            return None
        data = dict(row)
        data["payload"] = json.loads(data.pop("payload_json", "{}") or "{}")
        return data

    def _decode_feedback_row(self, row: Optional[sqlite3.Row]) -> Optional[Dict[str, Any]]:
        if row is None:
            return None
        data = dict(row)
        data["metadata"] = json.loads(data.pop("metadata_json", "{}") or "{}")
        return data
