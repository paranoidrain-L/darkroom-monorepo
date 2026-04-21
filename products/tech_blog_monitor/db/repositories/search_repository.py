"""Search repository with sqlite fallback and postgres FTS path."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Float, String, case, cast, func, literal, literal_column, or_, select
from sqlalchemy.orm import Session

from products.tech_blog_monitor.db.models import (
    ArticleContentModel,
    ArticleEnrichmentModel,
    ArticleModel,
    ArticleRelevanceModel,
    ArticleSearchDocumentModel,
)
from products.tech_blog_monitor.db.schema_manager import POSTGRES_ARTICLE_SEARCH_TSVECTOR_SQL


class SearchRepository:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.dialect_name = session.bind.dialect.name if session.bind is not None else "sqlite"

    @staticmethod
    def published_from_days(days: int) -> int | None:
        if days <= 0:
            return None
        now = datetime.now(timezone.utc)
        return int(now.timestamp()) - days * 86400

    def search_articles(
        self,
        *,
        query: str = "",
        source_name: str | None = None,
        category: str | None = None,
        topic: str | None = None,
        tag: str | None = None,
        published_from_ts: int | None = None,
        limit: int = 20,
    ) -> list[dict]:
        if self.dialect_name == "postgresql":
            results = self._search_articles_postgres(
                query=query,
                source_name=source_name,
                category=category,
                topic=topic,
                tag=tag,
                published_from_ts=published_from_ts,
                limit=limit,
            )
            if results:
                return results
        return self._search_articles_fallback(
            query=query,
            source_name=source_name,
            category=category,
            topic=topic,
            tag=tag,
            published_from_ts=published_from_ts,
            limit=limit,
        )

    def _base_join_stmt(self):
        return (
            select(ArticleModel, ArticleContentModel, ArticleEnrichmentModel, ArticleRelevanceModel)
            .outerjoin(ArticleContentModel, ArticleContentModel.article_id == ArticleModel.article_id)
            .outerjoin(ArticleEnrichmentModel, ArticleEnrichmentModel.article_id == ArticleModel.article_id)
            .outerjoin(ArticleRelevanceModel, ArticleRelevanceModel.article_id == ArticleModel.article_id)
        )

    def _search_articles_fallback(
        self,
        *,
        query: str,
        source_name: str | None,
        category: str | None,
        topic: str | None,
        tag: str | None,
        published_from_ts: int | None,
        limit: int,
    ) -> list[dict]:
        stmt = self._base_join_stmt()
        published_order = func.coalesce(ArticleModel.published_ts, ArticleModel.last_seen_at)
        if source_name:
            stmt = stmt.where(ArticleModel.source_name == source_name)
        if category:
            stmt = stmt.where(ArticleModel.category == category)
        if topic:
            stmt = stmt.where(ArticleEnrichmentModel.topic == topic)
        if tag:
            stmt = stmt.where(cast(ArticleEnrichmentModel.tags_json, String).like(f'%"{tag}"%'))
        if published_from_ts is not None:
            stmt = stmt.where(ArticleModel.published_ts >= published_from_ts)

        query_text = query.strip().lower()
        if query_text:
            like = f"%{query_text}%"
            stmt = stmt.where(
                or_(
                    func.lower(ArticleModel.title).like(like),
                    func.lower(ArticleModel.rss_summary).like(like),
                    func.lower(func.coalesce(ArticleContentModel.clean_text, "")).like(like),
                    func.lower(func.coalesce(ArticleEnrichmentModel.one_line_summary, "")).like(like),
                    func.lower(func.coalesce(ArticleEnrichmentModel.why_it_matters, "")).like(like),
                    func.lower(cast(func.coalesce(ArticleEnrichmentModel.tags_json, "[]"), String)).like(like),
                    func.lower(func.coalesce(ArticleEnrichmentModel.topic, "")).like(like),
                )
            )
        if query_text:
            like = f"%{query_text}%"
            score = cast(
                case((func.lower(ArticleModel.title).like(like), 30), else_=0)
                + case(
                    (func.lower(func.coalesce(ArticleEnrichmentModel.topic, "")).like(like), 20),
                    else_=0,
                )
                + case(
                    (
                        func.lower(
                            cast(func.coalesce(ArticleEnrichmentModel.tags_json, "[]"), String)
                        ).like(like),
                        15,
                    ),
                    else_=0,
                )
                + case(
                    (
                        func.lower(
                            func.coalesce(ArticleEnrichmentModel.one_line_summary, "")
                        ).like(like),
                        10,
                    ),
                    else_=0,
                )
                + case(
                    (func.lower(func.coalesce(ArticleContentModel.clean_text, "")).like(like), 5),
                    else_=0,
                ),
                Float,
            )
        else:
            score = literal(0.0)
        rows = self.session.execute(
            stmt.order_by(
                score.desc(),
                published_order.desc(),
                ArticleModel.updated_at.desc(),
            ).limit(limit)
        ).all()
        return [self._serialize_article_row(row) for row in rows]

    def _search_articles_postgres(
        self,
        *,
        query: str,
        source_name: str | None,
        category: str | None,
        topic: str | None,
        tag: str | None,
        published_from_ts: int | None,
        limit: int,
    ) -> list[dict]:
        if not self.session.execute(select(func.count()).select_from(ArticleSearchDocumentModel)).scalar():
            return []

        query_text = query.strip()
        published_order = func.coalesce(ArticleSearchDocumentModel.published_ts, ArticleModel.last_seen_at)
        vector_expr = literal_column(POSTGRES_ARTICLE_SEARCH_TSVECTOR_SQL)
        stmt = (
            select(
                ArticleSearchDocumentModel,
                ArticleModel,
                ArticleContentModel,
                ArticleEnrichmentModel,
                ArticleRelevanceModel,
            )
            .join(ArticleModel, ArticleModel.article_id == ArticleSearchDocumentModel.article_id)
            .outerjoin(ArticleContentModel, ArticleContentModel.article_id == ArticleModel.article_id)
            .outerjoin(ArticleEnrichmentModel, ArticleEnrichmentModel.article_id == ArticleModel.article_id)
            .outerjoin(ArticleRelevanceModel, ArticleRelevanceModel.article_id == ArticleModel.article_id)
        )
        if source_name:
            stmt = stmt.where(ArticleSearchDocumentModel.source_name == source_name)
        if category:
            stmt = stmt.where(ArticleSearchDocumentModel.category == category)
        if topic:
            stmt = stmt.where(ArticleSearchDocumentModel.topic == topic)
        if tag:
            stmt = stmt.where(cast(ArticleSearchDocumentModel.tags_json, String).like(f'%"{tag}"%'))
        if published_from_ts is not None:
            stmt = stmt.where(ArticleSearchDocumentModel.published_ts >= published_from_ts)
        if query_text:
            ts_query = func.websearch_to_tsquery("simple", query_text)
            stmt = stmt.where(vector_expr.op("@@")(ts_query))
            rank_expr = func.ts_rank_cd(vector_expr, ts_query)
        else:
            rank_expr = literal(0.0)

        rows = self.session.execute(
            stmt.order_by(
                rank_expr.desc(),
                published_order.desc(),
                ArticleModel.updated_at.desc(),
            ).limit(limit)
        ).all()
        return [
            self._serialize_article_row((article, content, enrichment, relevance))
            for _, article, content, enrichment, relevance in rows
        ]

    @staticmethod
    def _serialize_article_row(row) -> dict:
        article, content, enrichment, relevance = row
        return {
            "article_id": article.article_id,
            "normalized_url": article.normalized_url,
            "url": article.url,
            "source_id": article.source_id,
            "source_name": article.source_name,
            "category": article.category,
            "title": article.title,
            "published_ts": article.published_ts,
            "first_seen_at": article.first_seen_at,
            "last_seen_at": article.last_seen_at,
            "latest_fetched_at": article.latest_fetched_at,
            "rss_summary": article.rss_summary,
            "ai_summary": article.ai_summary,
            "content_hash": article.content_hash,
            "last_run_id": article.last_run_id,
            "created_at": article.created_at,
            "updated_at": article.updated_at,
            "content_status": content.content_status if content is not None else "not_fetched",
            "content_source": content.content_source if content is not None else "",
            "clean_text": content.clean_text if content is not None else "",
            "content_error": content.content_error if content is not None else "",
            "content_http_status": content.content_http_status if content is not None else None,
            "content_fetched_at": content.content_fetched_at if content is not None else None,
            "content_final_url": content.content_final_url if content is not None else "",
            "one_line_summary": enrichment.one_line_summary if enrichment is not None else "",
            "key_points": enrichment.key_points_json if enrichment is not None else [],
            "why_it_matters": enrichment.why_it_matters if enrichment is not None else "",
            "recommended_for": enrichment.recommended_for_json if enrichment is not None else [],
            "tags": enrichment.tags_json if enrichment is not None else [],
            "topic": enrichment.topic if enrichment is not None else "",
            "enrichment_status": (
                enrichment.enrichment_status if enrichment is not None else "not_enriched"
            ),
            "enrichment_error": enrichment.enrichment_error if enrichment is not None else "",
            "relevance_score": relevance.relevance_score if relevance is not None else 0.0,
            "relevance_level": relevance.relevance_level if relevance is not None else "not_evaluated",
            "relevance_reasons": relevance.relevance_reasons_json if relevance is not None else [],
            "matched_signals": relevance.matched_signals_json if relevance is not None else [],
            "dependency_match_score": (
                relevance.dependency_match_score if relevance is not None else 0.0
            ),
            "topic_match_score": relevance.topic_match_score if relevance is not None else 0.0,
            "source_priority_score": (
                relevance.source_priority_score if relevance is not None else 0.0
            ),
        }
