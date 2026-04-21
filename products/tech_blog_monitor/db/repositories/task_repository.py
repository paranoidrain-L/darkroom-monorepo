"""Task repository."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from products.tech_blog_monitor.db.models import TaskRecordModel


class TaskRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_task(
        self,
        *,
        task_id: str,
        task_type: str,
        task_status: str,
        trigger_source: str,
        requested_by: str,
        idempotency_key: str,
        scope: str,
        artifact_uri: str,
        input_payload: dict,
        result_payload: dict,
        max_retries: int,
        retry_count: int,
        started_at: int,
        finished_at: int | None,
        error_code: str = "",
        error_message: str = "",
    ) -> dict:
        row = TaskRecordModel(
            task_id=task_id,
            task_type=task_type,
            task_status=task_status,
            trigger_source=trigger_source,
            requested_by=requested_by,
            idempotency_key=idempotency_key,
            scope=scope,
            artifact_uri=artifact_uri,
            input_payload_json=input_payload,
            result_payload_json=result_payload,
            max_retries=max_retries,
            retry_count=retry_count,
            started_at=started_at,
            finished_at=finished_at,
            error_code=error_code,
            error_message=error_message,
        )
        self.session.add(row)
        self.session.flush()
        return self._serialize_task(row)

    def update_task(
        self,
        task_id: str,
        *,
        task_status: str,
        result_payload: dict,
        artifact_uri: str,
        finished_at: int,
        error_code: str = "",
        error_message: str = "",
    ) -> dict:
        row = self.session.get(TaskRecordModel, task_id)
        if row is None:
            raise ValueError(f"task not found: {task_id}")
        row.task_status = task_status
        row.result_payload_json = result_payload
        row.artifact_uri = artifact_uri
        row.finished_at = finished_at
        row.error_code = error_code
        row.error_message = error_message
        self.session.flush()
        return self._serialize_task(row)

    def get_task(self, task_id: str) -> dict | None:
        row = self.session.get(TaskRecordModel, task_id)
        return self._serialize_task(row) if row is not None else None

    def list_tasks(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
        task_type: str | None = None,
        task_types: list[str] | tuple[str, ...] | None = None,
        task_status: str | None = None,
    ) -> list[dict]:
        stmt = select(TaskRecordModel)
        if task_type:
            stmt = stmt.where(TaskRecordModel.task_type == task_type)
        if task_types:
            stmt = stmt.where(TaskRecordModel.task_type.in_(list(task_types)))
        if task_status:
            stmt = stmt.where(TaskRecordModel.task_status == task_status)
        rows = self.session.execute(
            stmt.order_by(TaskRecordModel.started_at.desc(), TaskRecordModel.task_id.desc())
            .limit(limit)
            .offset(offset)
        ).scalars()
        return [self._serialize_task(row) for row in rows]

    def get_latest_attempt(self, *, task_type: str, idempotency_key: str) -> dict | None:
        row = self.session.execute(
            select(TaskRecordModel)
            .where(TaskRecordModel.task_type == task_type)
            .where(TaskRecordModel.idempotency_key == idempotency_key)
            .order_by(TaskRecordModel.started_at.desc(), TaskRecordModel.task_id.desc())
            .limit(1)
        ).scalar_one_or_none()
        return self._serialize_task(row) if row is not None else None

    @staticmethod
    def _serialize_task(row: TaskRecordModel | None) -> dict | None:
        if row is None:
            return None
        return {
            "task_id": row.task_id,
            "task_type": row.task_type,
            "task_status": row.task_status,
            "trigger_source": row.trigger_source,
            "requested_by": row.requested_by,
            "idempotency_key": row.idempotency_key,
            "scope": row.scope,
            "artifact_uri": row.artifact_uri,
            "input_payload": dict(row.input_payload_json or {}),
            "result_payload": dict(row.result_payload_json or {}),
            "max_retries": row.max_retries,
            "retry_count": row.retry_count,
            "started_at": row.started_at,
            "finished_at": row.finished_at,
            "error_code": row.error_code,
            "error_message": row.error_message,
        }
