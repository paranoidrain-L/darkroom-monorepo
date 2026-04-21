# -*- coding: utf-8 -*-
"""Tech Blog Monitor monitor 单元测试。"""

import json
from datetime import datetime, timezone

from products.tech_blog_monitor.archive_store import ArchiveStore
from products.tech_blog_monitor.config import FeedSource, TechBlogMonitorConfig
from products.tech_blog_monitor.db.engine import build_sqlite_url, create_session_factory
from products.tech_blog_monitor.db.models import (
    ArticleRelevanceModel,
    ArticleSearchDocumentModel,
    ChunkEmbeddingRecordModel,
    RunModel,
)
from products.tech_blog_monitor.fetcher import Article, FeedHealth
from products.tech_blog_monitor.monitor import run
from products.tech_blog_monitor.qa import answer_question
from products.tech_blog_monitor.retrieval import RetrievalQuery
from products.tech_blog_monitor.search import SearchQuery, search_articles

_DUMMY_FEED = [FeedSource("Dummy", "https://dummy.com/rss", "测试")]

_ARTICLE = Article(
    title="Article A", url="https://example.com/a",
    published=datetime(2026, 4, 10, tzinfo=timezone.utc),
    rss_summary="raw summary", source_name="Source A", category="行业风向标",
    source_id="Source A::https://example.com/a",
    published_ts=1744243200, fetched_at=1744243200,
)
_HEALTH = [FeedHealth(name="Source A", url="https://example.com/feed", success=True, article_count=1)]


def _make_config(tmp_path, **kwargs):
    defaults = dict(feeds=_DUMMY_FEED, output_path=str(tmp_path / "report.md"))
    defaults.update(kwargs)
    return TechBlogMonitorConfig(**defaults)


def _patch(monkeypatch, captured):
    monkeypatch.setattr("products.tech_blog_monitor.monitor.fetch_all",
                        lambda cfg, **kwargs: ([_ARTICLE], _HEALTH))
    monkeypatch.setattr("products.tech_blog_monitor.monitor.fetch_contents",
                        lambda items, workers, timeout, max_chars, **kwargs: items)
    monkeypatch.setattr("products.tech_blog_monitor.monitor.analyze",
                        lambda items, backend: (items, "热点内容"))

    def mock_build(items, trend_md, health_list, new_urls=None, view="by_category",
                   incremental_mode="split", relevance_report=None):
        captured["items"] = items
        captured["view"] = view
        captured["health"] = health_list
        captured["new_urls"] = new_urls
        captured["incremental_mode"] = incremental_mode
        captured["relevance_report"] = relevance_report
        return f"report for {len(items)} articles"

    monkeypatch.setattr("products.tech_blog_monitor.monitor.build_report", mock_build)


def test_run_writes_report(monkeypatch, tmp_path):
    config = _make_config(tmp_path, ai_backend="codex")
    captured = {}
    _patch(monkeypatch, captured)

    exit_code = run(config)

    assert exit_code == 0
    assert (tmp_path / "report.md").read_text(encoding="utf-8") == "report for 1 articles"
    assert captured["health"] == _HEALTH


def test_run_passes_view_to_build_report(monkeypatch, tmp_path):
    config = _make_config(tmp_path, view="by_time")
    captured = {}
    _patch(monkeypatch, captured)

    run(config)

    assert captured["view"] == "by_time"


def test_run_passes_incremental_mode_to_build_report(monkeypatch, tmp_path):
    config = _make_config(tmp_path, state_path=str(tmp_path / "state.json"), incremental_mode="new_only")
    captured = {}
    _patch(monkeypatch, captured)

    run(config)

    assert captured["incremental_mode"] == "new_only"


def test_run_view_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("TECH_BLOG_VIEW", "by_time")
    config = _make_config(tmp_path)
    captured = {}
    _patch(monkeypatch, captured)

    run(config)

    assert captured["view"] == "by_time"
    monkeypatch.delenv("TECH_BLOG_VIEW")


def test_run_returns_nonzero_when_no_articles(monkeypatch, tmp_path):
    config = _make_config(tmp_path)
    monkeypatch.setattr("products.tech_blog_monitor.monitor.fetch_all", lambda cfg, **kwargs: ([], []))

    exit_code = run(config)

    assert exit_code == 1
    assert not (tmp_path / "report.md").exists()


# ── Phase 6: 增量状态 ─────────────────────────────────────────────────────────

def test_run_incremental_marks_new_urls(monkeypatch, tmp_path):
    """首次运行时所有文章都是新增，状态文件应被创建。"""
    state_path = str(tmp_path / "state.json")
    config = _make_config(tmp_path, state_path=state_path)
    captured = {}
    _patch(monkeypatch, captured)

    run(config)

    assert captured["new_urls"] == {_ARTICLE.url}
    assert (tmp_path / "state.json").exists()


def test_run_incremental_second_run_no_new(monkeypatch, tmp_path):
    """第二次运行时已见文章不再标为新增。"""
    state_path = str(tmp_path / "state.json")
    config = _make_config(tmp_path, state_path=state_path)
    captured = {}
    _patch(monkeypatch, captured)

    run(config)   # 第一次
    run(config)   # 第二次

    assert captured["new_urls"] == set()


def test_run_no_state_path_passes_none(monkeypatch, tmp_path):
    """未配置 state_path 时 new_urls 传 None 给 build_report。"""
    config = _make_config(tmp_path)  # state_path=""
    captured = {}
    _patch(monkeypatch, captured)

    run(config)

    assert captured["new_urls"] is None


# ── Phase 6: JSON 输出 ────────────────────────────────────────────────────────

def test_run_writes_json_output(monkeypatch, tmp_path):
    json_path = str(tmp_path / "output.json")
    config = _make_config(tmp_path, json_output_path=json_path)
    captured = {}
    _patch(monkeypatch, captured)

    run(config)

    assert (tmp_path / "output.json").exists()
    data = json.loads((tmp_path / "output.json").read_text())
    assert data["article_count"] == 1
    assert data["articles"][0]["url"] == _ARTICLE.url
    assert data["articles"][0]["content_status"] == "not_fetched"
    assert "feed_health" in data
    assert data["feed_health"][0]["source_type"] == "rss"
    assert data["run_summary"]["feed_stats"]["success"] == 1
    assert data["run_summary"]["stage_timings"]["fetch_feeds"]["status"] == "success"


def test_run_passes_content_fetch_settings(monkeypatch, tmp_path):
    config = _make_config(
        tmp_path,
        content_extractor="heuristic",
        playwright_fallback=False,
        playwright_timeout=12,
        playwright_workers=3,
    )
    captured = {}
    _patch(monkeypatch, captured)

    def _capture_fetch_contents(items, workers, timeout, max_chars, **kwargs):
        captured["content_kwargs"] = kwargs
        return items

    monkeypatch.setattr("products.tech_blog_monitor.monitor.fetch_contents", _capture_fetch_contents)

    run(config)

    assert captured["content_kwargs"] == {
        "content_extractor": "heuristic",
        "playwright_fallback": False,
        "playwright_timeout": 12,
        "playwright_workers": 3,
    }


def test_run_no_json_output_by_default(monkeypatch, tmp_path):
    config = _make_config(tmp_path)  # json_output_path=""
    captured = {}
    _patch(monkeypatch, captured)

    run(config)

    assert not any(f.suffix == ".json" for f in tmp_path.iterdir())


def test_run_new_only_filters_report_articles(monkeypatch, tmp_path):
    old_article = Article(
        title="Old",
        url="https://example.com/old",
        published=datetime(2026, 4, 9, tzinfo=timezone.utc),
        rss_summary="old summary",
        source_name="Source A",
        category="行业风向标",
        source_id="Source A::https://example.com/old",
        published_ts=1744156800,
        fetched_at=1744243200,
    )
    state_path = str(tmp_path / "state.json")
    config = _make_config(tmp_path, state_path=state_path, incremental_mode="new_only")
    captured = {}
    _patch(monkeypatch, captured)
    monkeypatch.setattr(
        "products.tech_blog_monitor.monitor.fetch_all",
        lambda cfg, **kwargs: ([_ARTICLE, old_article], _HEALTH),
    )

    with open(state_path, "w", encoding="utf-8") as f:
        json.dump({"https://example.com/old": 1}, f)

    run(config)

    assert [item.url for item in captured["items"]] == [_ARTICLE.url]
    assert captured["new_urls"] == {_ARTICLE.url}


def test_run_new_only_with_no_new_articles_still_writes_report(monkeypatch, tmp_path):
    state_path = str(tmp_path / "state.json")
    config = _make_config(tmp_path, state_path=state_path, incremental_mode="new_only")
    captured = {}
    _patch(monkeypatch, captured)
    monkeypatch.setattr(
        "products.tech_blog_monitor.monitor.analyze",
        lambda items, backend: (_ for _ in ()).throw(AssertionError("analyze should not be called")),
    )

    with open(state_path, "w", encoding="utf-8") as f:
        json.dump({_ARTICLE.url: 1}, f)

    exit_code = run(config)

    assert exit_code == 0
    assert captured["items"] == []
    assert (tmp_path / "report.md").read_text(encoding="utf-8") == "report for 0 articles"


def test_run_writes_history_archive(monkeypatch, tmp_path):
    archive_dir = tmp_path / "archive"
    config = _make_config(
        tmp_path,
        state_path=str(tmp_path / "state.json"),
        archive_dir=str(archive_dir),
    )
    captured = {}
    _patch(monkeypatch, captured)

    run(config)

    daily_dirs = list((archive_dir / "daily").iterdir())
    assert len(daily_dirs) == 1
    archived_files = list(daily_dirs[0].iterdir())
    assert any(path.suffix == ".md" for path in archived_files)
    assert any(path.suffix == ".json" for path in archived_files)
    assert (archive_dir / "latest.md").exists()
    assert (archive_dir / "latest.json").exists()


def test_run_writes_asset_db_when_configured(monkeypatch, tmp_path):
    db_path = tmp_path / "assets.db"
    config = _make_config(tmp_path, asset_db_path=str(db_path))
    captured = {}
    _patch(monkeypatch, captured)
    monkeypatch.setattr(
        "products.tech_blog_monitor.monitor.fetch_contents",
        lambda items, workers, timeout, max_chars, **kwargs: [
            Article(
                **{
                    **item.__dict__,
                    "content_status": "fetched",
                    "content_source": "html_article",
                    "clean_text": "正文内容",
                    "raw_html": "<article>正文内容</article>",
                    "content_final_url": item.url,
                    "content_fetched_at": 1744243201,
                }
            )
            for item in items
        ],
    )

    run(config)

    assert db_path.exists()
    with ArchiveStore(str(db_path)) as store:
        assert store.count_rows("runs") == 1
        assert store.count_rows("articles") == 1
        assert store.count_rows("run_articles") == 1
        saved = store.get_article_by_url(_ARTICLE.url)
        assert saved is not None
        assert saved["source_name"] == _ARTICLE.source_name
        assert saved["content_status"] == "fetched"
        assert saved["clean_text"] == "正文内容"


def test_run_mirrors_database_url_and_populates_auxiliary_tables(monkeypatch, tmp_path):
    target_db_path = tmp_path / "target.db"
    database_url = build_sqlite_url(str(target_db_path))
    config = _make_config(tmp_path, database_url=database_url)
    captured = {}
    _patch(monkeypatch, captured)
    monkeypatch.setattr(
        "products.tech_blog_monitor.monitor.fetch_contents",
        lambda items, workers, timeout, max_chars, **kwargs: [
            Article(
                **{
                    **item.__dict__,
                    "content_status": "fetched",
                    "content_source": "html_article",
                    "clean_text": "Persistent agent memory keeps workflow state across sessions.",
                    "raw_html": "<article>Persistent agent memory keeps workflow state across sessions.</article>",
                    "content_final_url": item.url,
                    "content_fetched_at": 1744243201,
                }
            )
            for item in items
        ],
    )

    run(config)

    session_factory = create_session_factory(database_url)
    with session_factory() as session:
        assert session.query(RunModel).count() == 1
        assert session.query(ArticleRelevanceModel).count() == 1
        assert session.query(ArticleSearchDocumentModel).count() == 1
        assert session.query(ChunkEmbeddingRecordModel).count() >= 1

    search_results = search_articles(
        "",
        SearchQuery(query="Article A"),
        database_url=database_url,
    )
    assert search_results[0]["title"] == "Article A"

    qa_result = answer_question(
        "",
        RetrievalQuery(question="How is workflow state preserved across sessions?", limit=1),
        database_url=database_url,
    )
    assert qa_result.status == "answered"
    assert qa_result.citations[0].url == _ARTICLE.url


def test_run_evaluates_internal_relevance_when_configured(monkeypatch, tmp_path):
    json_path = str(tmp_path / "output.json")
    config = _make_config(
        tmp_path,
        json_output_path=json_path,
        stack_profile_path=str(tmp_path / "stack_profile.yaml"),
        stack_repo_roots=[str(tmp_path / "repo")],
    )
    captured = {}
    _patch(monkeypatch, captured)
    monkeypatch.setattr(
        "products.tech_blog_monitor.monitor.load_stack_profile",
        lambda path: type(
            "Profile",
            (),
            {
                "signals": [],
                "source_priorities": {"rss": 0.6},
                "warnings": [],
            },
        )(),
    )
    monkeypatch.setattr(
        "products.tech_blog_monitor.monitor.scan_repo_roots",
        lambda roots: type(
            "ScanResult",
            (),
            {
                "signals": [],
                "scanned_files": [str(tmp_path / "repo" / "requirements.txt")],
                "warnings": [],
            },
        )(),
    )

    def _evaluate(items, **kwargs):
        items[0].relevance_score = 4.6
        items[0].relevance_level = "medium"
        items[0].relevance_reasons = ["dependency:fastapi 命中 title"]
        return items, __import__(
            "products.tech_blog_monitor.internal_relevance.models",
            fromlist=["RelevanceReport"],
        ).RelevanceReport(
            status="ok",
            summary="1/1 命中内部信号",
            signal_count=3,
            dependency_signal_count=2,
            topic_signal_count=1,
            article_count=1,
            matched_article_count=1,
            level_counts={"medium": 1},
            top_matches=[{"title": "Article A", "matched_signal_names": ["fastapi"], "relevance_score": 4.6, "relevance_level": "medium"}],
        )

    monkeypatch.setattr("products.tech_blog_monitor.monitor.evaluate_internal_relevance", _evaluate)

    run(config)

    assert captured["relevance_report"].status == "ok"
    data = json.loads((tmp_path / "output.json").read_text())
    assert data["relevance_report"]["matched_article_count"] == 1
    assert data["articles"][0]["relevance_level"] == "medium"


def test_run_relevance_failure_is_fail_open(monkeypatch, tmp_path):
    json_path = str(tmp_path / "output.json")
    config = _make_config(
        tmp_path,
        json_output_path=json_path,
        stack_profile_path=str(tmp_path / "stack_profile.yaml"),
    )
    captured = {}
    _patch(monkeypatch, captured)
    monkeypatch.setattr(
        "products.tech_blog_monitor.monitor.load_stack_profile",
        lambda path: (_ for _ in ()).throw(RuntimeError("profile parse failed")),
    )

    exit_code = run(config)

    assert exit_code == 0
    data = json.loads((tmp_path / "output.json").read_text())
    assert data["relevance_report"]["status"] == "skipped"
    assert "profile parse failed" in data["relevance_report"]["warnings"][0]
    assert data["run_summary"]["stage_timings"]["evaluate_relevance"]["status"] == "failed"


def test_run_dispatches_deliveries_when_configured(monkeypatch, tmp_path):
    db_path = tmp_path / "assets.db"
    json_path = tmp_path / "output.json"
    config = _make_config(
        tmp_path,
        asset_db_path=str(db_path),
        json_output_path=str(json_path),
        delivery_webhook_url="https://example.com/webhook",
        delivery_roles=["executive"],
    )
    captured = {}
    _patch(monkeypatch, captured)
    monkeypatch.setattr(
        "products.tech_blog_monitor.monitor.analyze_insights",
        lambda db_path, query: type(
            "InsightReport",
            (),
            {
                "status": "ok",
                "summary": "智能体主题持续上升。",
                "topic_clusters": [],
                "source_comparisons": [],
                "timeline": [],
                "hot_signals": [],
            },
        )(),
    )
    monkeypatch.setattr(
        "products.tech_blog_monitor.monitor.maybe_dispatch_deliveries",
        lambda **kwargs: [{"role": "executive", "status": "delivered"}],
    )

    run(config)

    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["deliveries"][0]["status"] == "delivered"
    assert "run_id" in data


def test_run_without_delivery_config_does_not_dispatch(monkeypatch, tmp_path):
    db_path = tmp_path / "assets.db"
    config = _make_config(tmp_path, asset_db_path=str(db_path))
    captured = {}
    _patch(monkeypatch, captured)
    monkeypatch.setattr(
        "products.tech_blog_monitor.monitor.maybe_dispatch_deliveries",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("should not dispatch")),
    )

    run(config)


def test_run_is_not_interrupted_by_delivery_sender_exception(monkeypatch, tmp_path):
    db_path = tmp_path / "assets.db"
    json_path = tmp_path / "output.json"
    state_path = tmp_path / "state.json"
    config = _make_config(
        tmp_path,
        asset_db_path=str(db_path),
        json_output_path=str(json_path),
        state_path=str(state_path),
        delivery_webhook_url="https://example.com/webhook",
        delivery_roles=["executive"],
    )
    captured = {}
    _patch(monkeypatch, captured)
    monkeypatch.setattr(
        "products.tech_blog_monitor.monitor.analyze_insights",
        lambda db_path, query: type(
            "InsightReport",
            (),
            {
                "status": "ok",
                "summary": "智能体主题持续上升。",
                "topic_clusters": [],
                "source_comparisons": [],
                "timeline": [],
                "hot_signals": [],
            },
        )(),
    )

    def _raise_sender(url, payload):
        raise RuntimeError("webhook down")

    monkeypatch.setattr(
        "products.tech_blog_monitor.monitor.maybe_dispatch_deliveries",
        lambda **kwargs: __import__("products.tech_blog_monitor.delivery", fromlist=["maybe_dispatch_deliveries"]).maybe_dispatch_deliveries(
            **kwargs,
            sender=_raise_sender,
            now_ts=1744675200,
        ),
    )

    exit_code = run(config)

    assert exit_code == 0
    assert json_path.exists()
    assert state_path.exists()
    with ArchiveStore(str(db_path)) as store:
        deliveries = store.list_deliveries()
        assert len(deliveries) == 1
        assert deliveries[0]["status"] == "pending"
        assert deliveries[0]["attempt_count"] == 1
