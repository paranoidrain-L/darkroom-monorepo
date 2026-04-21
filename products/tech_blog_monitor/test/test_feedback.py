# -*- coding: utf-8 -*-
"""Tech Blog Monitor Phase 7 feedback tests."""

import json
from datetime import datetime, timezone

import pytest

from products.tech_blog_monitor.archive_store import ArchiveStore
from products.tech_blog_monitor.db.engine import build_sqlite_url
from products.tech_blog_monitor.feedback import list_feedback, record_feedback
from products.tech_blog_monitor.feedback_cli import main as feedback_cli_main
from products.tech_blog_monitor.fetcher import Article


def _build_store(tmp_path):
    db_path = tmp_path / "assets.db"
    published = datetime(2025, 4, 15, tzinfo=timezone.utc)
    article = Article(
        title="Agent Memory Systems",
        url="https://example.com/a",
        source_name="OpenAI News",
        category="AI Agent/工程实践",
        source_id="OpenAI News::https://example.com/a",
        rss_summary="summary",
        published=published,
        published_ts=int(published.timestamp()),
        fetched_at=int(published.timestamp()),
    )
    with ArchiveStore(str(db_path)) as store:
        run_id = store.record_run(
            generated_at=int(published.timestamp()),
            generated_at_iso="2025-04-15T00:00:00+00:00",
            output_path="/tmp/report.md",
            view="by_category",
            incremental_mode="split",
            all_articles=[article],
            report_articles=[article],
            new_urls={article.url},
        )
    return str(db_path), run_id


def test_record_feedback_persists_and_lists(tmp_path):
    db_path, run_id = _build_store(tmp_path)
    feedback_id = record_feedback(
        db_path,
        run_id=run_id,
        role="engineer",
        feedback_type="like",
        feedback_text="useful",
        metadata={"section": "summary"},
        created_at=1744675200,
    )
    assert feedback_id
    rows = list_feedback(db_path, run_id=run_id)
    assert len(rows) == 1
    assert rows[0]["feedback_text"] == "useful"
    assert rows[0]["metadata"]["section"] == "summary"


def test_record_feedback_missing_run_raises(tmp_path):
    db_path, _ = _build_store(tmp_path)
    with pytest.raises(ValueError):
        record_feedback(
            db_path,
            run_id="missing",
            role="engineer",
            feedback_type="like",
            feedback_text="useful",
            metadata={},
            created_at=1744675200,
        )


def test_feedback_uses_database_url_when_provided(tmp_path):
    db_path, run_id = _build_store(tmp_path)
    feedback_id = record_feedback(
        str(tmp_path / "missing.db"),
        run_id=run_id,
        role="engineer",
        feedback_type="like",
        feedback_text="useful",
        metadata={"source": "database_url"},
        created_at=1744675200,
        database_url=build_sqlite_url(db_path),
    )
    assert feedback_id.startswith("feedback_")
    rows = list_feedback(
        str(tmp_path / "missing.db"),
        run_id=run_id,
        database_url=build_sqlite_url(db_path),
    )
    assert rows[0]["metadata"]["source"] == "database_url"


def test_feedback_cli_add_and_list(monkeypatch, tmp_path, capsys):
    db_path, run_id = _build_store(tmp_path)
    monkeypatch.setattr(
        "sys.argv",
        [
            "feedback_cli.py",
            "add",
            "--db",
            db_path,
            "--run-id",
            run_id,
            "--role",
            "researcher",
            "--type",
            "bookmark",
            "--text",
            "keep this",
            "--metadata",
            '{"priority": "high"}',
        ],
    )
    with pytest.raises(SystemExit) as exc:
        feedback_cli_main()
    assert exc.value.code == 0
    capsys.readouterr()

    monkeypatch.setattr(
        "sys.argv",
        [
            "feedback_cli.py",
            "list",
            "--db",
            db_path,
            "--run-id",
            run_id,
        ],
    )
    with pytest.raises(SystemExit) as exc:
        feedback_cli_main()
    assert exc.value.code == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data[0]["role"] == "researcher"
    assert data[0]["metadata"]["priority"] == "high"
