"""Delivery repository."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from products.tech_blog_monitor.db.models import DeliveryModel


class DeliveryRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_deliveries(self, *, run_id: str | None = None, status: str | None = None) -> list[dict]:
        stmt = select(DeliveryModel).order_by(DeliveryModel.created_at.asc(), DeliveryModel.delivery_id.asc())
        if run_id:
            stmt = stmt.where(DeliveryModel.run_id == run_id)
        if status:
            stmt = stmt.where(DeliveryModel.status == status)
        rows = self.session.execute(stmt).scalars()
        return [
            {
                "delivery_id": row.delivery_id,
                "run_id": row.run_id,
                "role": row.role,
                "cadence": row.cadence,
                "dedupe_key": row.dedupe_key,
                "payload": row.payload_json,
                "status": row.status,
                "attempt_count": row.attempt_count,
                "last_error": row.last_error,
                "delivered_at": row.delivered_at,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }
            for row in rows
        ]
