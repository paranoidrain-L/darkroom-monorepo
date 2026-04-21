# -*- coding: utf-8 -*-
"""Task runner tests for P2.3."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select

from products.tech_blog_monitor.archive_store import ArchiveStore
from products.tech_blog_monitor.config import FeedSource, TechBlogMonitorConfig
from products.tech_blog_monitor.db.engine import build_sqlite_url
from products.tech_blog_monitor.db.models import (
    ArticleSearchDocumentModel,
    ChunkEmbeddingRecordModel,
)
from products.tech_blog_monitor.fetcher import Article
from products.tech_blog_monitor.repository_provider import open_repository_bundle
from products.tech_blog_monitor.tasks import (
    LocalTaskRunner,
    TaskRequest,
    build_task_idempotency_key,
)


def _config(tmp_path, **kwargs) -> TechBlogMonitorConfig:
    defaults = {
        "feeds": [FeedSource("Dummy", "https://dummy.com/rss", "测试")],
        "output_path": str(tmp_path / "report.md"),
    }
    defaults.update(kwargs)
    return TechBlogMonitorConfig(**defaults)


def _article(url: str = "https://example.com/a") -> Article:
    published = datetime(2026, 4, 10, tzinfo=timezone.utc)
    article = Article(
        title="Article A",
        url=url,
        source_name="Source A",
        category="行业风向标",
        source_id=f"Source A::{url}",
        rss_summary="raw summary",
        published=published,
        published_ts=int(published.timestamp()),
        fetched_at=int(published.timestamp()),
        clean_text="structured article content",
        content_status="fetched",
        content_source="trafilatura",
    )
    article.one_line_summary = "summary"
    article.why_it_matters = "matters"
    article.topic = "智能体"
    article.tags = ["agent"]
    article.enrichment_status = "enriched"
    return article


def _build_store(tmp_path) -> str:
    db_path = tmp_path / "assets.db"
    article = _article()
    with ArchiveStore(str(db_path)) as store:
        store.record_run(
            generated_at=1744675200,
            generated_at_iso="2025-04-15T00:00:00+00:00",
            output_path="/tmp/report.md",
            view="by_category",
            incremental_mode="split",
            all_articles=[article],
            report_articles=[article],
            new_urls={article.url},
        )
    return str(db_path)


def test_build_task_idempotency_key_is_stable_for_same_semantics():
    left = build_task_idempotency_key(
        task_type="manual_run",
        trigger_source="cli",
        scope="report:/tmp/report.md",
        input_payload={
            "view": "by_category",
            "nested": {"b": 2, "a": 1},
            "feeds_count": 1,
        },
    )
    right = build_task_idempotency_key(
        task_type="manual_run",
        trigger_source="cli",
        scope="report:/tmp/report.md",
        input_payload={
            "feeds_count": 1,
            "nested": {"a": 1, "b": 2},
            "view": "by_category",
        },
    )

    assert left == right
    assert left.startswith("manual_run:")


def test_task_request_autogenerates_stable_idempotency_key():
    first = TaskRequest(
        task_type="rebuild_search_index",
        trigger_source="cli",
        requested_by="cli",
        scope="search_index:/tmp/assets.db",
        input_payload={"asset_db_path": "/tmp/assets.db"},
    )
    second = TaskRequest(
        task_type="rebuild_search_index",
        trigger_source="cli",
        requested_by="operator",
        scope="search_index:/tmp/assets.db",
        input_payload={"asset_db_path": "/tmp/assets.db"},
    )

    assert first.idempotency_key == second.idempotency_key
    assert first.requested_by == "cli"
    assert second.requested_by == "operator"


def test_local_task_runner_persists_manual_run_task(monkeypatch, tmp_path):
    config = _config(tmp_path)
    runner = LocalTaskRunner(config)

    def _fake_run(cfg, **kwargs):
        observer = kwargs["observer"]
        observer.run_summaries.append(
            {
                "run_id": "run_fake",
                "asset_run_id": "asset_fake",
                "status": "success",
            }
        )
        assert kwargs["task_type"] == "manual_run"
        assert kwargs["task_id"].startswith("task_manual_run_")
        return 0

    monkeypatch.setattr("products.tech_blog_monitor.monitor.run", _fake_run)

    exit_code = runner.run_monitor(
        config,
        task_type="manual_run",
        trigger_source="cli",
        requested_by="cli",
    )

    assert exit_code == 0
    task_db_path = tmp_path / "tech_blog_tasks.db"
    with open_repository_bundle(database_url=build_sqlite_url(str(task_db_path))) as bundle:
        tasks = bundle.task_repository.list_tasks()
    assert len(tasks) == 1
    assert tasks[0]["task_type"] == "manual_run"
    assert tasks[0]["task_status"] == "succeeded"
    assert tasks[0]["trigger_source"] == "cli"
    assert tasks[0]["artifact_uri"] == str(tmp_path / "report.md")
    assert tasks[0]["result_payload"]["run_summary"]["asset_run_id"] == "asset_fake"
    assert set(tasks[0]) >= {
        "task_id",
        "task_type",
        "task_status",
        "trigger_source",
        "requested_by",
        "idempotency_key",
        "scope",
        "artifact_uri",
        "input_payload",
        "result_payload",
        "max_retries",
        "retry_count",
        "started_at",
        "finished_at",
        "error_code",
        "error_message",
    }


@pytest.mark.parametrize(
    ("task_type", "trigger_source"),
    [
        ("manual_run", "cli"),
        ("scheduled_run", "scheduler"),
    ],
)
def test_local_task_runner_marks_nonzero_exit_code_as_failed(
    monkeypatch,
    tmp_path,
    task_type,
    trigger_source,
):
    config = _config(tmp_path)
    runner = LocalTaskRunner(config)

    def _fake_run(cfg, **kwargs):
        observer = kwargs["observer"]
        observer.run_summaries.append(
            {
                "run_id": f"run_{task_type}",
                "asset_run_id": "",
                "status": "failed",
                "error_code": "NoArticles",
            }
        )
        return 1

    monkeypatch.setattr("products.tech_blog_monitor.monitor.run", _fake_run)

    exit_code = runner.run_monitor(
        config,
        task_type=task_type,
        trigger_source=trigger_source,
        requested_by=trigger_source,
    )

    assert exit_code == 1
    task_db_path = tmp_path / "tech_blog_tasks.db"
    with open_repository_bundle(database_url=build_sqlite_url(str(task_db_path))) as bundle:
        tasks = bundle.task_repository.list_tasks(task_type=task_type)
    assert tasks[0]["task_status"] == "failed"
    assert tasks[0]["error_code"] == "NonZeroExitCode"
    assert tasks[0]["result_payload"]["exit_code"] == 1
    assert tasks[0]["result_payload"]["run_summary"]["status"] == "failed"


def test_local_task_runner_failure_keeps_run_summary(monkeypatch, tmp_path):
    config = _config(tmp_path)
    runner = LocalTaskRunner(config)

    def _fake_run(cfg, **kwargs):
        observer = kwargs["observer"]
        observer.run_summaries.append(
            {
                "run_id": "run_failed",
                "asset_run_id": "",
                "status": "failed",
                "error_code": "RuntimeError",
            }
        )
        raise RuntimeError("run failed")

    monkeypatch.setattr("products.tech_blog_monitor.monitor.run", _fake_run)

    with pytest.raises(RuntimeError):
        runner.run_monitor(
            config,
            task_type="manual_run",
            trigger_source="cli",
            requested_by="cli",
        )

    task_db_path = tmp_path / "tech_blog_tasks.db"
    with open_repository_bundle(database_url=build_sqlite_url(str(task_db_path))) as bundle:
        tasks = bundle.task_repository.list_tasks()
    assert tasks[0]["task_status"] == "failed"
    assert tasks[0]["result_payload"]["run_summary"]["status"] == "failed"
    assert tasks[0]["error_code"] == "RuntimeError"


def test_local_task_runner_tracks_retry_count(tmp_path):
    config = _config(tmp_path)
    runner = LocalTaskRunner(config)

    def _fail():
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        runner.run(
            "demo_task",
            _fail,
            trigger_source="cli",
            requested_by="cli",
            input_payload={"scope": "same"},
            scope="demo",
        )
    with pytest.raises(RuntimeError):
        runner.run(
            "demo_task",
            _fail,
            trigger_source="cli",
            requested_by="cli",
            input_payload={"scope": "same"},
            scope="demo",
        )

    task_db_path = tmp_path / "tech_blog_tasks.db"
    with open_repository_bundle(database_url=build_sqlite_url(str(task_db_path))) as bundle:
        tasks = bundle.task_repository.list_tasks(task_type="demo_task")
    assert len(tasks) == 2
    assert sorted(task["retry_count"] for task in tasks) == [0, 1]
    assert {task["task_status"] for task in tasks} == {"failed"}


def test_rebuild_search_index_records_task_and_backfills_documents(tmp_path):
    db_path = _build_store(tmp_path)
    config = _config(tmp_path, asset_db_path=db_path)
    runner = LocalTaskRunner(config)

    result = runner.rebuild_search_index(
        requested_by="cli",
        trigger_source="cli",
    )

    assert result["documents_upserted"] == 1
    with open_repository_bundle(asset_db_path=db_path) as bundle:
        document_count = bundle.session.execute(
            select(func.count()).select_from(ArticleSearchDocumentModel)
        ).scalar_one()
        tasks = bundle.task_repository.list_tasks(task_type="rebuild_search_index")
    assert document_count == 1
    assert tasks[0]["task_status"] == "succeeded"
    assert tasks[0]["scope"] == f"search_index:{db_path}"


def test_rebuild_retrieval_index_records_task_and_backfills_embeddings(tmp_path):
    db_path = _build_store(tmp_path)
    config = _config(tmp_path, asset_db_path=db_path)
    runner = LocalTaskRunner(config)

    result = runner.rebuild_retrieval_index(
        requested_by="cli",
        trigger_source="cli",
    )

    assert result["records_upserted"] >= 1
    with open_repository_bundle(asset_db_path=db_path) as bundle:
        embedding_count = bundle.session.execute(
            select(func.count()).select_from(ChunkEmbeddingRecordModel)
        ).scalar_one()
        tasks = bundle.task_repository.list_tasks(task_type="rebuild_retrieval_index")
    assert embedding_count >= 1
    assert tasks[0]["task_status"] == "succeeded"
    assert tasks[0]["scope"] == f"retrieval_index:{db_path}"
