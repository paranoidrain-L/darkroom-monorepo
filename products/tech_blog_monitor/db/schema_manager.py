"""Schema bootstrap and explicit backfill helpers."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from products.tech_blog_monitor.db.engine import create_engine_for_url, create_session_factory
from products.tech_blog_monitor.db.models import (
    ArticleChunkModel,
    ArticleContentModel,
    ArticleEnrichmentModel,
    ArticleModel,
    ArticleRelevanceModel,
    ArticleSearchDocumentModel,
    Base,
    ChunkEmbeddingRecordModel,
    DeliveryModel,
    FeedbackModel,
    MetaKV,
    RunArticleModel,
    RunModel,
    TaskRecordModel,
)

POSTGRES_ARTICLE_SEARCH_TSVECTOR_SQL = "to_tsvector('simple', coalesce(document_text, ''))"

_SQLITE_TO_MODEL_MAPPINGS = (
    ("meta", MetaKV, {}),
    ("runs", RunModel, {}),
    ("articles", ArticleModel, {}),
    ("run_articles", RunArticleModel, {}),
    ("article_contents", ArticleContentModel, {}),
    (
        "article_enrichments",
        ArticleEnrichmentModel,
        {
            "key_points_json": lambda value: json.loads(value or "[]"),
            "recommended_for_json": lambda value: json.loads(value or "[]"),
            "tags_json": lambda value: json.loads(value or "[]"),
        },
    ),
    (
        "article_chunks",
        ArticleChunkModel,
        {"embedding_json": lambda value: json.loads(value or "[]")},
    ),
    (
        "article_relevances",
        ArticleRelevanceModel,
        {
            "relevance_reasons_json": lambda value: json.loads(value or "[]"),
            "matched_signals_json": lambda value: json.loads(value or "[]"),
        },
    ),
    (
        "deliveries",
        DeliveryModel,
        {"payload_json": lambda value: json.loads(value or "{}")},
    ),
    (
        "feedback",
        FeedbackModel,
        {"metadata_json": lambda value: json.loads(value or "{}")},
    ),
    (
        "task_records",
        TaskRecordModel,
        {
            "input_payload_json": lambda value: json.loads(value or "{}"),
            "result_payload_json": lambda value: json.loads(value or "{}"),
        },
    ),
)


def build_search_document_text(
    *,
    title: str = "",
    topic: str = "",
    one_line_summary: str = "",
    why_it_matters: str = "",
    rss_summary: str = "",
    ai_summary: str = "",
    clean_text: str = "",
    tags: list[str] | None = None,
) -> str:
    clean_tags = [tag for tag in (tags or []) if isinstance(tag, str) and tag]
    weighted_parts = [
        title,
        title,
        title,
        topic,
        topic,
        " ".join(clean_tags),
        " ".join(clean_tags),
        one_line_summary,
        why_it_matters,
        rss_summary,
        ai_summary,
        clean_text,
    ]
    return "\n".join(part for part in weighted_parts if part)


def build_chunk_document_text(
    *,
    title: str = "",
    topic: str = "",
    text_value: str = "",
) -> str:
    weighted_parts = [
        title,
        title,
        topic,
        text_value,
    ]
    return "\n".join(part for part in weighted_parts if part)


def _ensure_postgres_features(session: Session) -> None:
    if session.bind is None or session.bind.dialect.name != "postgresql":
        return
    session.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    session.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_article_search_documents_fts "
            f"ON article_search_documents USING GIN ({POSTGRES_ARTICLE_SEARCH_TSVECTOR_SQL})"
        )
    )


def bootstrap_schema(database_url: str) -> None:
    engine = create_engine_for_url(database_url)
    with engine.begin() as connection:
        if connection.dialect.name == "postgresql":
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        Base.metadata.create_all(connection)
        if connection.dialect.name == "postgresql":
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_article_search_documents_fts "
                    f"ON article_search_documents USING GIN ({POSTGRES_ARTICLE_SEARCH_TSVECTOR_SQL})"
                )
            )


def backfill_article_search_documents(session: Session) -> int:
    rows = session.execute(
        select(
            ArticleModel.article_id,
            ArticleModel.title,
            ArticleModel.url,
            ArticleModel.source_name,
            ArticleModel.category,
            ArticleModel.published_ts,
            ArticleModel.rss_summary,
            ArticleModel.ai_summary,
            ArticleContentModel.clean_text,
            ArticleEnrichmentModel.one_line_summary,
            ArticleEnrichmentModel.why_it_matters,
            ArticleEnrichmentModel.topic,
            ArticleEnrichmentModel.tags_json,
            ArticleModel.updated_at,
        )
        .outerjoin(ArticleContentModel, ArticleContentModel.article_id == ArticleModel.article_id)
        .outerjoin(ArticleEnrichmentModel, ArticleEnrichmentModel.article_id == ArticleModel.article_id)
    ).all()

    inserted = 0
    for row in rows:
        tags = row.tags_json or []
        session.merge(
            ArticleSearchDocumentModel(
                article_id=row.article_id,
                title=row.title or "",
                url=row.url or "",
                source_name=row.source_name or "",
                category=row.category or "",
                published_ts=row.published_ts,
                rss_summary=row.rss_summary or "",
                ai_summary=row.ai_summary or "",
                one_line_summary=row.one_line_summary or "",
                why_it_matters=row.why_it_matters or "",
                topic=row.topic or "",
                tags_json=list(tags),
                clean_text=row.clean_text or "",
                document_text=build_search_document_text(
                    title=row.title or "",
                    topic=row.topic or "",
                    one_line_summary=row.one_line_summary or "",
                    why_it_matters=row.why_it_matters or "",
                    rss_summary=row.rss_summary or "",
                    ai_summary=row.ai_summary or "",
                    clean_text=row.clean_text or "",
                    tags=list(tags),
                ),
                updated_at=row.updated_at,
            )
        )
        inserted += 1
    session.flush()
    return inserted


def backfill_chunk_embedding_records(session: Session) -> int:
    rows = session.execute(
        select(
            ArticleChunkModel.chunk_id,
            ArticleChunkModel.article_id,
            ArticleChunkModel.chunk_index,
            ArticleChunkModel.source_kind,
            ArticleChunkModel.text,
            ArticleChunkModel.embedding_json,
            ArticleChunkModel.updated_at,
            ArticleModel.title,
            ArticleModel.url,
            ArticleModel.source_name,
            ArticleModel.category,
            ArticleModel.published_ts,
            ArticleEnrichmentModel.topic,
        )
        .join(ArticleModel, ArticleModel.article_id == ArticleChunkModel.article_id)
        .outerjoin(ArticleEnrichmentModel, ArticleEnrichmentModel.article_id == ArticleChunkModel.article_id)
    ).all()

    inserted = 0
    for row in rows:
        session.merge(
            ChunkEmbeddingRecordModel(
                chunk_id=row.chunk_id,
                article_id=row.article_id,
                chunk_index=row.chunk_index,
                title=row.title or "",
                url=row.url or "",
                source_name=row.source_name or "",
                category=row.category or "",
                topic=row.topic or "",
                published_ts=row.published_ts,
                source_kind=row.source_kind or "",
                text=row.text or "",
                document_text=build_chunk_document_text(
                    title=row.title or "",
                    topic=row.topic or "",
                    text_value=row.text or "",
                ),
                embedding_json=row.embedding_json or [],
                embedding_vector=row.embedding_json or [],
                updated_at=row.updated_at,
            )
        )
        inserted += 1
    session.flush()
    return inserted


def mirror_sqlite_asset_db(source_db_path: str, database_url: str) -> None:
    source_path = Path(source_db_path)
    if not source_path.exists():
        raise FileNotFoundError(f"资产库不存在: {source_db_path}")

    bootstrap_schema(database_url)
    session_factory = create_session_factory(database_url)
    with sqlite3.connect(str(source_path)) as source_conn, session_factory() as target_session:
        source_conn.row_factory = sqlite3.Row
        available_tables = {
            row["name"]
            for row in source_conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        _ensure_postgres_features(target_session)
        for table_name, model, decoders in _SQLITE_TO_MODEL_MAPPINGS:
            if table_name not in available_tables:
                continue
            rows = source_conn.execute(f"SELECT * FROM {table_name}").fetchall()
            for row in rows:
                payload = dict(row)
                for column_name, decoder in decoders.items():
                    payload[column_name] = decoder(payload.get(column_name))
                target_session.merge(model(**payload))
            target_session.flush()
        backfill_article_search_documents(target_session)
        backfill_chunk_embedding_records(target_session)
        target_session.commit()
