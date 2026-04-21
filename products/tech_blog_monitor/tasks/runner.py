# -*- coding: utf-8 -*-
"""Task runner implementations for P2.3."""

from __future__ import annotations

import time
from inspect import Parameter, signature
from pathlib import Path
from typing import Any, Callable, Protocol
from uuid import uuid4

from products.tech_blog_monitor.config import TechBlogMonitorConfig
from products.tech_blog_monitor.db.engine import build_sqlite_url, resolve_database_url
from products.tech_blog_monitor.db.schema_manager import (
    backfill_article_search_documents,
    backfill_chunk_embedding_records,
    bootstrap_schema,
)
from products.tech_blog_monitor.observability import InMemoryObserver
from products.tech_blog_monitor.repository_provider import open_repository_bundle
from products.tech_blog_monitor.tasks.models import (
    TaskExecutionRecord,
    TaskRequest,
    TaskRetryPolicy,
)


class TaskRunner(Protocol):
    def run(self, task_type: str, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any: ...


def _utc_ts() -> int:
    return int(time.time())


def _default_task_id(task_type: str) -> str:
    return f"task_{task_type}_{_utc_ts()}_{uuid4().hex[:8]}"


def _coerce_result_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if value is None:
        return {}
    return {"value": value}


def _accepts_task_record(fn: Callable[..., Any]) -> bool:
    params = signature(fn).parameters.values()
    for param in params:
        if param.kind == Parameter.VAR_KEYWORD:
            return True
    return "task_record" in signature(fn).parameters


def _default_result_status(_: Any) -> tuple[str, str, str]:
    return ("succeeded", "", "")


class LocalTaskRunner:
    """Persist task records while keeping monitor.run as the business core."""

    def __init__(self, config: TechBlogMonitorConfig) -> None:
        self.config = config
        self.last_task_id = ""
        self.last_task_status = ""

    def _sidecar_task_db_path(self) -> str:
        output_path = Path(self.config.output_path).expanduser().resolve()
        return str(output_path.parent / "tech_blog_tasks.db")

    def _resolve_task_storage_database_url(self) -> str:
        if self.config.database_url.strip() or self.config.asset_db_path.strip():
            return resolve_database_url(config=self.config)
        return build_sqlite_url(self._sidecar_task_db_path())

    def _resolve_operational_database_url(
        self,
        *,
        asset_db_path: str = "",
        database_url: str = "",
    ) -> str:
        return resolve_database_url(
            config=self.config,
            asset_db_path=asset_db_path,
            database_url=database_url,
        )

    def _create_task_record(
        self,
        request: TaskRequest,
    ) -> tuple[str, TaskExecutionRecord]:
        storage_database_url = self._resolve_task_storage_database_url()
        bootstrap_schema(storage_database_url)
        with open_repository_bundle(database_url=storage_database_url) as bundle:
            previous = bundle.task_repository.get_latest_attempt(
                task_type=request.task_type,
                idempotency_key=request.idempotency_key,
            )
            retry_count = int(previous["retry_count"]) + 1 if previous is not None else 0
            started_at = _utc_ts()
            task_id = _default_task_id(request.task_type)
            bundle.task_repository.create_task(
                task_id=task_id,
                task_type=request.task_type,
                task_status="running",
                trigger_source=request.trigger_source,
                requested_by=request.requested_by,
                idempotency_key=request.idempotency_key,
                scope=request.scope,
                artifact_uri=request.artifact_uri,
                input_payload=request.input_payload,
                result_payload={},
                max_retries=request.retry_policy.max_retries,
                retry_count=retry_count,
                started_at=started_at,
                finished_at=None,
            )
        self.last_task_id = task_id
        self.last_task_status = "running"
        return storage_database_url, TaskExecutionRecord(
            task_id=task_id,
            task_type=request.task_type,
            task_status="running",
            trigger_source=request.trigger_source,
            requested_by=request.requested_by,
            idempotency_key=request.idempotency_key,
            scope=request.scope,
            artifact_uri=request.artifact_uri,
            input_payload=dict(request.input_payload),
            result_payload={},
            max_retries=request.retry_policy.max_retries,
            retry_count=retry_count,
            started_at=started_at,
            finished_at=None,
        )

    def _finish_task_record(
        self,
        storage_database_url: str,
        task_record: TaskExecutionRecord,
        *,
        task_status: str,
        result_payload: dict[str, Any],
        artifact_uri: str,
        error_code: str = "",
        error_message: str = "",
    ) -> None:
        with open_repository_bundle(database_url=storage_database_url) as bundle:
            bundle.task_repository.update_task(
                task_record.task_id,
                task_status=task_status,
                result_payload=result_payload,
                artifact_uri=artifact_uri,
                finished_at=_utc_ts(),
                error_code=error_code,
                error_message=error_message,
            )
        self.last_task_status = task_status

    def _execute_request(
        self,
        request: TaskRequest,
        fn: Callable[[TaskExecutionRecord], Any],
        *,
        result_builder: Callable[[Any], dict[str, Any]] | None = None,
        error_result_builder: Callable[[Exception], dict[str, Any]] | None = None,
        result_status_resolver: Callable[[Any], tuple[str, str, str]] | None = None,
    ) -> Any:
        storage_database_url, task_record = self._create_task_record(request)
        try:
            value = fn(task_record)
        except Exception as exc:
            failure_payload = (
                error_result_builder(exc)
                if error_result_builder is not None
                else {
                    "error_code": exc.__class__.__name__,
                    "error_message": str(exc),
                }
            )
            self._finish_task_record(
                storage_database_url,
                task_record,
                task_status="failed",
                result_payload=failure_payload,
                artifact_uri=request.artifact_uri,
                error_code=exc.__class__.__name__,
                error_message=str(exc),
            )
            raise

        result_payload = (
            result_builder(value) if result_builder is not None else _coerce_result_payload(value)
        )
        task_status, error_code, error_message = (
            result_status_resolver(value)
            if result_status_resolver is not None
            else _default_result_status(value)
        )
        self._finish_task_record(
            storage_database_url,
            task_record,
            task_status=task_status,
            result_payload=result_payload,
            artifact_uri=request.artifact_uri,
            error_code=error_code,
            error_message=error_message,
        )
        return value

    def run(
        self,
        task_type: str,
        fn: Callable[..., Any],
        *args: Any,
        trigger_source: str = "manual",
        requested_by: str = "",
        input_payload: dict[str, Any] | None = None,
        scope: str = "",
        artifact_uri: str = "",
        idempotency_key: str = "",
        retry_policy: TaskRetryPolicy | None = None,
        result_builder: Callable[[Any], dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> Any:
        request = TaskRequest(
            task_type=task_type,
            trigger_source=trigger_source,
            requested_by=requested_by or trigger_source,
            input_payload=dict(input_payload or {}),
            scope=scope,
            artifact_uri=artifact_uri,
            idempotency_key=idempotency_key,
            retry_policy=retry_policy or TaskRetryPolicy(),
        )
        return self._execute_request(
            request,
            (
                lambda task_record: fn(*args, task_record=task_record, **kwargs)
                if _accepts_task_record(fn)
                else fn(*args, **kwargs)
            ),
            result_builder=result_builder,
        )

    def run_monitor(
        self,
        config: TechBlogMonitorConfig,
        *,
        task_type: str,
        trigger_source: str,
        requested_by: str,
        input_payload_extra: dict[str, Any] | None = None,
    ) -> int:
        request = TaskRequest(
            task_type=task_type,
            trigger_source=trigger_source,
            requested_by=requested_by,
            input_payload={
                "output_path": config.output_path,
                "view": config.view,
                "incremental_mode": config.incremental_mode,
                "fetch_content": config.fetch_content,
                "asset_db_path": config.asset_db_path,
                "database_url_configured": bool(config.database_url.strip()),
                "feeds_count": len(config.feeds),
                **dict(input_payload_extra or {}),
            },
            scope=f"report:{config.output_path}",
            artifact_uri=config.output_path,
        )
        observer = InMemoryObserver()

        def _invoke(task_record: TaskExecutionRecord) -> int:
            from products.tech_blog_monitor.monitor import run as monitor_run

            return monitor_run(
                config,
                observer=observer,
                task_id=task_record.task_id,
                task_type=task_type,
            )

        def _result_builder(exit_code: int) -> dict[str, Any]:
            summary = observer.run_summaries[-1] if observer.run_summaries else {}
            return {
                "exit_code": exit_code,
                "output_path": config.output_path,
                "run_summary": summary,
            }

        def _error_result_builder(exc: Exception) -> dict[str, Any]:
            summary = observer.run_summaries[-1] if observer.run_summaries else {}
            return {
                "error_code": exc.__class__.__name__,
                "error_message": str(exc),
                "output_path": config.output_path,
                "run_summary": summary,
            }

        def _result_status_resolver(exit_code: int) -> tuple[str, str, str]:
            if exit_code == 0:
                return ("succeeded", "", "")
            return (
                "failed",
                "NonZeroExitCode",
                f"monitor.run returned exit code {exit_code}",
            )

        return self._execute_request(
            request,
            _invoke,
            result_builder=_result_builder,
            error_result_builder=_error_result_builder,
            result_status_resolver=_result_status_resolver,
        )

    def rebuild_search_index(
        self,
        *,
        asset_db_path: str = "",
        database_url: str = "",
        requested_by: str = "cli",
        trigger_source: str = "cli",
    ) -> dict[str, Any]:
        resolved_asset_db_path = asset_db_path or self.config.asset_db_path
        resolved_database_url = self._resolve_operational_database_url(
            asset_db_path=asset_db_path,
            database_url=database_url,
        )
        request = TaskRequest(
            task_type="rebuild_search_index",
            trigger_source=trigger_source,
            requested_by=requested_by,
            input_payload={
                "asset_db_path": resolved_asset_db_path,
                "database_url_configured": bool(database_url or self.config.database_url.strip()),
            },
            scope=f"search_index:{resolved_asset_db_path or 'database_url'}",
        )

        def _invoke(_: TaskExecutionRecord) -> dict[str, Any]:
            bootstrap_schema(resolved_database_url)
            with open_repository_bundle(database_url=resolved_database_url) as bundle:
                upserted = backfill_article_search_documents(bundle.session)
            return {
                "documents_upserted": upserted,
                "target": "database_url" if (database_url or self.config.database_url.strip()) else "asset_db_path",
            }

        return self._execute_request(request, _invoke)

    def rebuild_retrieval_index(
        self,
        *,
        asset_db_path: str = "",
        database_url: str = "",
        requested_by: str = "cli",
        trigger_source: str = "cli",
    ) -> dict[str, Any]:
        resolved_asset_db_path = asset_db_path or self.config.asset_db_path
        resolved_database_url = self._resolve_operational_database_url(
            asset_db_path=asset_db_path,
            database_url=database_url,
        )
        request = TaskRequest(
            task_type="rebuild_retrieval_index",
            trigger_source=trigger_source,
            requested_by=requested_by,
            input_payload={
                "asset_db_path": resolved_asset_db_path,
                "database_url_configured": bool(database_url or self.config.database_url.strip()),
            },
            scope=f"retrieval_index:{resolved_asset_db_path or 'database_url'}",
        )

        def _invoke(_: TaskExecutionRecord) -> dict[str, Any]:
            bootstrap_schema(resolved_database_url)
            with open_repository_bundle(database_url=resolved_database_url) as bundle:
                upserted = backfill_chunk_embedding_records(bundle.session)
            return {
                "records_upserted": upserted,
                "target": "database_url" if (database_url or self.config.database_url.strip()) else "asset_db_path",
            }

        return self._execute_request(request, _invoke)
