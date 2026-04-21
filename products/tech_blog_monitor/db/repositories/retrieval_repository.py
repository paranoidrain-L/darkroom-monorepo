"""Retrieval repository."""

from __future__ import annotations

from sqlalchemy import String, cast, desc, func, or_, select
from sqlalchemy.orm import Session

from products.tech_blog_monitor.db.models import (
    ArticleChunkModel,
    ArticleEnrichmentModel,
    ArticleModel,
    ChunkEmbeddingRecordModel,
)
from products.tech_blog_monitor.retrieval import (
    build_fake_embedding,
    get_configured_embedding_provider_name,
    tokenize,
)

_CANDIDATE_MULTIPLIER = 8
_MAX_QUERY_TERMS = 8


class RetrievalRepository:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.dialect_name = session.bind.dialect.name if session.bind is not None else "sqlite"

    def retrieve_chunks(
        self,
        *,
        question: str,
        limit: int = 25,
        embedding_provider_name: str | None = None,
    ) -> list[dict]:
        provider_name = (embedding_provider_name or get_configured_embedding_provider_name()).strip().lower()
        if self.dialect_name == "postgresql" and provider_name == "fake":
            native = self._retrieve_chunks_postgres(question=question, limit=limit)
            if native:
                return native
        if self.dialect_name == "postgresql":
            text_rows = self._retrieve_chunks_postgres_text(question=question, limit=limit)
            if text_rows:
                return text_rows
        return self._retrieve_chunks_fallback(question=question, limit=limit)

    def _retrieve_chunks_fallback(self, *, question: str, limit: int) -> list[dict]:
        question_terms = self._query_terms(question)
        stmt = (
            select(ArticleChunkModel, ArticleModel, ArticleEnrichmentModel)
            .join(ArticleModel, ArticleModel.article_id == ArticleChunkModel.article_id)
            .outerjoin(ArticleEnrichmentModel, ArticleEnrichmentModel.article_id == ArticleModel.article_id)
        )
        if question_terms:
            stmt = stmt.where(or_(*self._sqlite_like_filters(question_terms)))
        rows = self.session.execute(
            stmt.order_by(
                func.coalesce(ArticleModel.published_ts, ArticleModel.updated_at).desc(),
                ArticleChunkModel.chunk_index.asc(),
            ).limit(limit * _CANDIDATE_MULTIPLIER)
        ).all()
        if not rows and question_terms:
            rows = self.session.execute(
                stmt.order_by(
                    func.coalesce(ArticleModel.published_ts, ArticleModel.updated_at).desc(),
                    ArticleChunkModel.chunk_index.asc(),
                ).limit(limit)
            ).all()
        return [self._serialize_fallback_row(row) for row in rows]

    def _retrieve_chunks_postgres(self, *, question: str, limit: int) -> list[dict]:
        if not self.session.execute(select(func.count()).select_from(ChunkEmbeddingRecordModel)).scalar():
            return []

        query_embedding = build_fake_embedding(question)
        stmt = select(ChunkEmbeddingRecordModel)
        try:
            rows = self.session.execute(
                stmt.where(ChunkEmbeddingRecordModel.embedding_vector.is_not(None))
                .order_by(
                    ChunkEmbeddingRecordModel.embedding_vector.cosine_distance(query_embedding).asc(),
                    desc(func.coalesce(ChunkEmbeddingRecordModel.published_ts, 0)),
                    ChunkEmbeddingRecordModel.chunk_index.asc(),
                )
                .limit(limit * 8)
            ).scalars().all()
            if rows:
                return [self._serialize_vector_row(row) for row in rows[:limit]]
        except Exception:
            self.session.rollback()

        rows = self.session.execute(
            stmt.order_by(
                desc(func.coalesce(ChunkEmbeddingRecordModel.published_ts, 0)),
                ChunkEmbeddingRecordModel.chunk_index.asc(),
            ).limit(limit * 32)
        ).scalars()
        ranked = []
        for row in rows:
            embedding = row.embedding_vector or row.embedding_json or []
            ranked.append(
                (
                    self._cosine_similarity(query_embedding, embedding),
                    row,
                )
            )
        ranked.sort(key=lambda item: (item[0], item[1].published_ts or 0, -item[1].chunk_index), reverse=True)
        return [self._serialize_vector_row(row) for _, row in ranked[:limit]]

    def _retrieve_chunks_postgres_text(self, *, question: str, limit: int) -> list[dict]:
        stmt = select(ChunkEmbeddingRecordModel)
        question_terms = self._query_terms(question)
        if question_terms:
            stmt = stmt.where(or_(*self._postgres_like_filters(question_terms)))
        rows = self.session.execute(
            stmt.order_by(
                desc(func.coalesce(ChunkEmbeddingRecordModel.published_ts, 0)),
                ChunkEmbeddingRecordModel.chunk_index.asc(),
            ).limit(limit * _CANDIDATE_MULTIPLIER)
        ).scalars().all()
        return [self._serialize_vector_row(row) for row in rows]

    @staticmethod
    def _query_terms(question: str) -> list[str]:
        terms: list[str] = []
        seen: set[str] = set()
        for token in tokenize(question):
            normalized = token.strip().lower()
            if not normalized or normalized in seen or normalized.isdigit():
                continue
            if len(normalized) == 1 and not ("\u4e00" <= normalized <= "\u9fff"):
                continue
            seen.add(normalized)
            terms.append(normalized)
            if len(terms) >= _MAX_QUERY_TERMS:
                break
        return terms

    @staticmethod
    def _sqlite_like_filters(question_terms: list[str]) -> list:
        filters = []
        for term in question_terms:
            like = f"%{term}%"
            filters.extend(
                [
                    func.lower(ArticleChunkModel.text).like(like),
                    func.lower(ArticleModel.title).like(like),
                    func.lower(func.coalesce(ArticleEnrichmentModel.topic, "")).like(like),
                    func.lower(func.coalesce(ArticleEnrichmentModel.one_line_summary, "")).like(like),
                    func.lower(func.coalesce(ArticleEnrichmentModel.why_it_matters, "")).like(like),
                    func.lower(cast(func.coalesce(ArticleEnrichmentModel.tags_json, "[]"), String)).like(like),
                ]
            )
        return filters

    @staticmethod
    def _postgres_like_filters(question_terms: list[str]) -> list:
        filters = []
        for term in question_terms:
            like = f"%{term}%"
            filters.extend(
                [
                    func.lower(ChunkEmbeddingRecordModel.title).like(like),
                    func.lower(func.coalesce(ChunkEmbeddingRecordModel.topic, "")).like(like),
                    func.lower(func.coalesce(ChunkEmbeddingRecordModel.text, "")).like(like),
                    func.lower(func.coalesce(ChunkEmbeddingRecordModel.document_text, "")).like(like),
                ]
            )
        return filters

    @staticmethod
    def _cosine_similarity(left: list[float], right: list[float]) -> float:
        if not left or not right or len(left) != len(right):
            return 0.0
        return sum(a * b for a, b in zip(left, right))

    @staticmethod
    def _serialize_fallback_row(row) -> dict:
        chunk, article, enrichment = row
        return {
            "chunk_id": chunk.chunk_id,
            "article_id": chunk.article_id,
            "chunk_index": chunk.chunk_index,
            "source_kind": chunk.source_kind,
            "text": chunk.text,
            "embedding": chunk.embedding_json,
            "title": article.title,
            "url": article.url,
            "source_name": article.source_name,
            "category": article.category,
            "published_ts": article.published_ts,
            "topic": enrichment.topic if enrichment is not None else "",
            "one_line_summary": enrichment.one_line_summary if enrichment is not None else "",
            "why_it_matters": enrichment.why_it_matters if enrichment is not None else "",
            "tags": enrichment.tags_json if enrichment is not None else [],
            "rss_summary": article.rss_summary,
        }

    @staticmethod
    def _serialize_vector_row(row: ChunkEmbeddingRecordModel) -> dict:
        return {
            "chunk_id": row.chunk_id,
            "article_id": row.article_id,
            "chunk_index": row.chunk_index,
            "source_kind": row.source_kind,
            "text": row.text,
            "embedding": row.embedding_vector or row.embedding_json,
            "title": row.title,
            "url": row.url,
            "source_name": row.source_name,
            "category": row.category,
            "published_ts": row.published_ts,
            "topic": row.topic,
            "one_line_summary": "",
            "why_it_matters": "",
            "tags": [],
            "rss_summary": "",
        }
