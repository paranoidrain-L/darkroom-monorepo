"""SQLAlchemy ORM models for tech_blog_monitor."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

try:
    from pgvector.sqlalchemy import Vector
except Exception:  # pragma: no cover - optional import
    Vector = None


class Base(DeclarativeBase):
    pass


class JSONText(TypeDecorator):
    impl = Text
    cache_ok = True

    def process_bind_param(self, value: Any, dialect) -> str:
        if value is None:
            return "[]"
        return json.dumps(value, ensure_ascii=False)

    def process_result_value(self, value: str | None, dialect) -> Any:
        if value in (None, ""):
            return []
        return json.loads(value)


class JSONDictText(TypeDecorator):
    impl = Text
    cache_ok = True

    def process_bind_param(self, value: Any, dialect) -> str:
        if value is None:
            return "{}"
        return json.dumps(value, ensure_ascii=False)

    def process_result_value(self, value: str | None, dialect) -> Any:
        if value in (None, ""):
            return {}
        return json.loads(value)


class EmbeddingVectorType(TypeDecorator):
    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql" and Vector is not None:
            return dialect.type_descriptor(Vector(64))
        return dialect.type_descriptor(Text())

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if dialect.name == "postgresql" and Vector is not None:
            return value
        return json.dumps(value, ensure_ascii=False)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if dialect.name == "postgresql" and Vector is not None:
            return list(value)
        return json.loads(value)


class MetaKV(Base):
    __tablename__ = "meta"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(String, nullable=False)


class RunModel(Base):
    __tablename__ = "runs"

    run_id: Mapped[str] = mapped_column(String, primary_key=True)
    generated_at: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    generated_at_iso: Mapped[str] = mapped_column(String, nullable=False)
    output_path: Mapped[str] = mapped_column(String, nullable=False)
    view: Mapped[str] = mapped_column(String, nullable=False)
    incremental_mode: Mapped[str] = mapped_column(String, nullable=False)
    article_count: Mapped[int] = mapped_column(Integer, nullable=False)
    all_article_count: Mapped[int] = mapped_column(Integer, nullable=False)
    new_article_count: Mapped[int] = mapped_column(Integer, nullable=False)


class ArticleModel(Base):
    __tablename__ = "articles"

    article_id: Mapped[str] = mapped_column(String, primary_key=True)
    normalized_url: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    url: Mapped[str] = mapped_column(String, nullable=False)
    source_id: Mapped[str] = mapped_column(String, nullable=False)
    source_name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    category: Mapped[str] = mapped_column(String, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    published_ts: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    first_seen_at: Mapped[int] = mapped_column(Integer, nullable=False)
    last_seen_at: Mapped[int] = mapped_column(Integer, nullable=False)
    latest_fetched_at: Mapped[int] = mapped_column(Integer, nullable=False)
    rss_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    ai_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    content_hash: Mapped[str] = mapped_column(String, nullable=False)
    last_run_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[int] = mapped_column(Integer, nullable=False)


class RunArticleModel(Base):
    __tablename__ = "run_articles"
    __table_args__ = (
        Index("idx_run_articles_run_id", "run_id"),
        Index("idx_run_articles_report_position", "run_id", "report_position"),
    )

    run_id: Mapped[str] = mapped_column(ForeignKey("runs.run_id"), primary_key=True)
    article_id: Mapped[str] = mapped_column(ForeignKey("articles.article_id"), primary_key=True)
    normalized_url: Mapped[str] = mapped_column(String, nullable=False)
    url: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    source_name: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    published_ts: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fetched_at: Mapped[int] = mapped_column(Integer, nullable=False)
    is_new: Mapped[int] = mapped_column(Integer, nullable=False)
    in_report: Mapped[int] = mapped_column(Integer, nullable=False)
    report_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rss_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    ai_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    content_hash: Mapped[str] = mapped_column(String, nullable=False)


class ArticleContentModel(Base):
    __tablename__ = "article_contents"

    article_id: Mapped[str] = mapped_column(ForeignKey("articles.article_id"), primary_key=True)
    content_status: Mapped[str] = mapped_column(String, nullable=False, default="not_fetched")
    content_source: Mapped[str] = mapped_column(String, nullable=False, default="")
    clean_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    raw_html: Mapped[str] = mapped_column(Text, nullable=False, default="")
    content_error: Mapped[str] = mapped_column(Text, nullable=False, default="")
    content_http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content_fetched_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content_final_url: Mapped[str] = mapped_column(String, nullable=False, default="")
    updated_at: Mapped[int] = mapped_column(Integer, nullable=False)


class ArticleEnrichmentModel(Base):
    __tablename__ = "article_enrichments"

    article_id: Mapped[str] = mapped_column(ForeignKey("articles.article_id"), primary_key=True)
    one_line_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    key_points_json: Mapped[list[Any]] = mapped_column(JSONText(), nullable=False, default=list)
    why_it_matters: Mapped[str] = mapped_column(Text, nullable=False, default="")
    recommended_for_json: Mapped[list[Any]] = mapped_column(JSONText(), nullable=False, default=list)
    tags_json: Mapped[list[Any]] = mapped_column(JSONText(), nullable=False, default=list)
    topic: Mapped[str] = mapped_column(String, nullable=False, default="")
    enrichment_status: Mapped[str] = mapped_column(String, nullable=False, default="not_enriched")
    enrichment_error: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_at: Mapped[int] = mapped_column(Integer, nullable=False)


class ArticleRelevanceModel(Base):
    __tablename__ = "article_relevances"

    article_id: Mapped[str] = mapped_column(ForeignKey("articles.article_id"), primary_key=True)
    relevance_score: Mapped[float] = mapped_column(nullable=False, default=0.0)
    relevance_level: Mapped[str] = mapped_column(String, nullable=False, default="not_evaluated")
    relevance_reasons_json: Mapped[list[Any]] = mapped_column(JSONText(), nullable=False, default=list)
    matched_signals_json: Mapped[list[Any]] = mapped_column(JSONText(), nullable=False, default=list)
    dependency_match_score: Mapped[float] = mapped_column(nullable=False, default=0.0)
    topic_match_score: Mapped[float] = mapped_column(nullable=False, default=0.0)
    source_priority_score: Mapped[float] = mapped_column(nullable=False, default=0.0)
    updated_at: Mapped[int] = mapped_column(Integer, nullable=False)


class ArticleChunkModel(Base):
    __tablename__ = "article_chunks"
    __table_args__ = (
        UniqueConstraint("article_id", "chunk_index", name="uq_article_chunks_article_index"),
        Index("idx_article_chunks_article_id", "article_id"),
    )

    chunk_id: Mapped[str] = mapped_column(String, primary_key=True)
    article_id: Mapped[str] = mapped_column(ForeignKey("articles.article_id"), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    source_kind: Mapped[str] = mapped_column(String, nullable=False, default="")
    text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    embedding_json: Mapped[list[Any]] = mapped_column(JSONText(), nullable=False, default=list)
    updated_at: Mapped[int] = mapped_column(Integer, nullable=False)


class DeliveryModel(Base):
    __tablename__ = "deliveries"

    delivery_id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.run_id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String, nullable=False)
    cadence: Mapped[str] = mapped_column(String, nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSONDictText(), nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String, nullable=False, index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str] = mapped_column(Text, nullable=False, default="")
    delivered_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[int] = mapped_column(Integer, nullable=False)


class FeedbackModel(Base):
    __tablename__ = "feedback"

    feedback_id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.run_id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String, nullable=False)
    feedback_type: Mapped[str] = mapped_column(String, nullable=False)
    feedback_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONDictText(), nullable=False, default=dict)
    created_at: Mapped[int] = mapped_column(Integer, nullable=False)


class TaskRecordModel(Base):
    __tablename__ = "task_records"

    task_id: Mapped[str] = mapped_column(String, primary_key=True)
    task_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    task_status: Mapped[str] = mapped_column(String, nullable=False, index=True)
    trigger_source: Mapped[str] = mapped_column(String, nullable=False, index=True)
    requested_by: Mapped[str] = mapped_column(String, nullable=False, default="")
    idempotency_key: Mapped[str] = mapped_column(String, nullable=False, index=True)
    scope: Mapped[str] = mapped_column(String, nullable=False, default="")
    artifact_uri: Mapped[str] = mapped_column(String, nullable=False, default="")
    input_payload_json: Mapped[dict[str, Any]] = mapped_column(JSONDictText(), nullable=False, default=dict)
    result_payload_json: Mapped[dict[str, Any]] = mapped_column(JSONDictText(), nullable=False, default=dict)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    finished_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str] = mapped_column(String, nullable=False, default="")
    error_message: Mapped[str] = mapped_column(Text, nullable=False, default="")


class ArticleSearchDocumentModel(Base):
    __tablename__ = "article_search_documents"

    article_id: Mapped[str] = mapped_column(ForeignKey("articles.article_id"), primary_key=True)
    title: Mapped[str] = mapped_column(String, nullable=False, default="")
    url: Mapped[str] = mapped_column(String, nullable=False, default="")
    source_name: Mapped[str] = mapped_column(String, nullable=False, default="")
    category: Mapped[str] = mapped_column(String, nullable=False, default="")
    published_ts: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rss_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    ai_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    one_line_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    why_it_matters: Mapped[str] = mapped_column(Text, nullable=False, default="")
    topic: Mapped[str] = mapped_column(String, nullable=False, default="")
    tags_json: Mapped[list[Any]] = mapped_column(JSONText(), nullable=False, default=list)
    clean_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    document_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_at: Mapped[int] = mapped_column(Integer, nullable=False)


class ChunkEmbeddingRecordModel(Base):
    __tablename__ = "chunk_embedding_records"
    __table_args__ = (
        Index("idx_chunk_embedding_records_article_id", "article_id"),
        Index("idx_chunk_embedding_records_published_ts", "published_ts"),
    )

    chunk_id: Mapped[str] = mapped_column(String, primary_key=True)
    article_id: Mapped[str] = mapped_column(ForeignKey("articles.article_id"), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False, default="")
    url: Mapped[str] = mapped_column(String, nullable=False, default="")
    source_name: Mapped[str] = mapped_column(String, nullable=False, default="")
    category: Mapped[str] = mapped_column(String, nullable=False, default="")
    topic: Mapped[str] = mapped_column(String, nullable=False, default="")
    published_ts: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_kind: Mapped[str] = mapped_column(String, nullable=False, default="")
    text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    document_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    embedding_json: Mapped[list[Any]] = mapped_column(JSONText(), nullable=False, default=list)
    embedding_vector: Mapped[list[float] | None] = mapped_column(EmbeddingVectorType(), nullable=True)
    updated_at: Mapped[int] = mapped_column(Integer, nullable=False)
