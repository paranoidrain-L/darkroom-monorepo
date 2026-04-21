"""Feedback repository."""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from products.tech_blog_monitor.db.models import FeedbackModel, RunModel


class FeedbackRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add_feedback(
        self,
        *,
        run_id: str,
        role: str,
        feedback_type: str,
        feedback_text: str,
        metadata: dict[str, object],
        created_at: int,
    ) -> str:
        if self.session.get(RunModel, run_id) is None:
            raise ValueError(f"run_id 不存在: {run_id}")
        feedback_id = f"feedback_{uuid4().hex[:12]}"
        row = FeedbackModel(
            feedback_id=feedback_id,
            run_id=run_id,
            role=role,
            feedback_type=feedback_type,
            feedback_text=feedback_text,
            metadata_json=metadata,
            created_at=created_at,
        )
        self.session.add(row)
        self.session.flush()
        return feedback_id

    def list_feedback(self, *, run_id: str | None = None, role: str | None = None) -> list[dict]:
        stmt = select(FeedbackModel).order_by(FeedbackModel.created_at.asc(), FeedbackModel.feedback_id.asc())
        if run_id:
            stmt = stmt.where(FeedbackModel.run_id == run_id)
        if role:
            stmt = stmt.where(FeedbackModel.role == role)
        rows = self.session.execute(stmt).scalars()
        return [
            {
                "feedback_id": row.feedback_id,
                "run_id": row.run_id,
                "role": row.role,
                "feedback_type": row.feedback_type,
                "feedback_text": row.feedback_text,
                "metadata": row.metadata_json,
                "created_at": row.created_at,
            }
            for row in rows
        ]
