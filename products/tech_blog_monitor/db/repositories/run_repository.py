"""Run repository."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from products.tech_blog_monitor.db.models import RunArticleModel, RunModel


class RunRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_runs(self, *, limit: int = 20, offset: int = 0) -> list[dict]:
        rows = self.session.execute(
            select(RunModel)
            .order_by(RunModel.generated_at.desc(), RunModel.run_id.desc())
            .limit(limit)
            .offset(offset)
        ).scalars()
        return [self._serialize_run(row) for row in rows]

    def get_run(self, run_id: str) -> dict | None:
        row = self.session.get(RunModel, run_id)
        return self._serialize_run(row) if row is not None else None

    def list_run_articles(self, run_id: str) -> list[dict]:
        rows = self.session.execute(
            select(RunArticleModel)
            .where(RunArticleModel.run_id == run_id)
            .order_by(
                RunArticleModel.report_position.is_(None),
                RunArticleModel.report_position.asc(),
                RunArticleModel.published_ts.desc(),
            )
        ).scalars()
        return [self._serialize_run_article(row) for row in rows]

    @staticmethod
    def _serialize_run(row: RunModel | None) -> dict | None:
        if row is None:
            return None
        return {
            "run_id": row.run_id,
            "generated_at": row.generated_at,
            "generated_at_iso": row.generated_at_iso,
            "output_path": row.output_path,
            "view": row.view,
            "incremental_mode": row.incremental_mode,
            "article_count": row.article_count,
            "all_article_count": row.all_article_count,
            "new_article_count": row.new_article_count,
        }

    @staticmethod
    def _serialize_run_article(row: RunArticleModel) -> dict:
        return {
            "run_id": row.run_id,
            "article_id": row.article_id,
            "normalized_url": row.normalized_url,
            "url": row.url,
            "title": row.title,
            "source_name": row.source_name,
            "category": row.category,
            "published_ts": row.published_ts,
            "fetched_at": row.fetched_at,
            "is_new": row.is_new,
            "in_report": row.in_report,
            "report_position": row.report_position,
            "rss_summary": row.rss_summary,
            "ai_summary": row.ai_summary,
            "content_hash": row.content_hash,
        }
