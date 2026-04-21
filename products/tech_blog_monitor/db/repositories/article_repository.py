"""Article repository."""

from __future__ import annotations

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from products.tech_blog_monitor.db.models import (
    ArticleContentModel,
    ArticleEnrichmentModel,
    ArticleModel,
    ArticleRelevanceModel,
)


class ArticleRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_article(self, article_id: str) -> dict | None:
        row = self.session.execute(
            self._article_select().where(ArticleModel.article_id == article_id)
        ).first()
        return self._serialize_article_row(row) if row is not None else None

    def get_article_by_url(self, normalized_url: str) -> dict | None:
        row = self.session.execute(
            self._article_select().where(ArticleModel.normalized_url == normalized_url)
        ).first()
        return self._serialize_article_row(row) if row is not None else None

    def list_articles(
        self,
        *,
        source_name: str | None = None,
        category: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        stmt = self._article_select()
        if source_name:
            stmt = stmt.where(ArticleModel.source_name == source_name)
        if category:
            stmt = stmt.where(ArticleModel.category == category)
        rows = self.session.execute(stmt.limit(limit)).all()
        return [self._serialize_article_row(row) for row in rows]

    @staticmethod
    def _article_select() -> Select:
        return (
            select(ArticleModel, ArticleContentModel, ArticleEnrichmentModel, ArticleRelevanceModel)
            .outerjoin(ArticleContentModel, ArticleContentModel.article_id == ArticleModel.article_id)
            .outerjoin(ArticleEnrichmentModel, ArticleEnrichmentModel.article_id == ArticleModel.article_id)
            .outerjoin(ArticleRelevanceModel, ArticleRelevanceModel.article_id == ArticleModel.article_id)
            .order_by(
                func.coalesce(ArticleModel.published_ts, ArticleModel.last_seen_at).desc(),
                ArticleModel.updated_at.desc(),
            )
        )

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
            "raw_html": content.raw_html if content is not None else "",
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
