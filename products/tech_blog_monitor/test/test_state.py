# -*- coding: utf-8 -*-
"""Tech Blog Monitor state 单元测试。"""

import json
import time

from products.tech_blog_monitor.fetcher import Article
from products.tech_blog_monitor.state import ArticleStateStore


def _article(url="https://a.com/1", title="Title", source_name="Source", category="分类", published_ts=1234):
    return Article(
        title=title,
        url=url,
        source_name=source_name,
        category=category,
        source_id=f"{source_name}::{url}",
        rss_summary="summary",
        published=None,
        published_ts=published_ts,
        fetched_at=9999,
    )


def test_new_store_is_empty(tmp_path):
    store = ArticleStateStore(str(tmp_path / "state.json"))
    assert len(store) == 0


def test_mark_and_is_seen(tmp_path):
    store = ArticleStateStore(str(tmp_path / "state.json"))
    store.mark_seen("https://a.com/1", 1000)
    assert store.is_seen("https://a.com/1")
    assert not store.is_seen("https://a.com/2")


def test_mark_seen_does_not_overwrite(tmp_path):
    store = ArticleStateStore(str(tmp_path / "state.json"))
    store.mark_seen("https://a.com/1", 1000)
    store.mark_seen("https://a.com/1", 9999)  # 重复标记
    store.save()
    store2 = ArticleStateStore(str(tmp_path / "state.json"))
    # first_seen 保持首次值，last_seen 更新为最新值
    assert store2._state["https://a.com/1"].first_seen_at == 1000
    assert store2._state["https://a.com/1"].last_seen_at == 9999


def test_new_urls_returns_unseen(tmp_path):
    store = ArticleStateStore(str(tmp_path / "state.json"))
    store.mark_seen("https://a.com/old", 1000)
    result = store.new_urls({"https://a.com/old", "https://a.com/new"})
    assert result == {"https://a.com/new"}


def test_save_and_reload(tmp_path):
    path = str(tmp_path / "state.json")
    store = ArticleStateStore(path)
    store.mark_seen("https://a.com/1", 1000)
    store.save()

    store2 = ArticleStateStore(path)
    assert store2.is_seen("https://a.com/1")
    assert len(store2) == 1


def test_load_missing_file_starts_empty(tmp_path):
    store = ArticleStateStore(str(tmp_path / "nonexistent.json"))
    assert len(store) == 0


def test_load_corrupted_file_starts_empty(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("not valid json{{{")
    store = ArticleStateStore(str(path))
    assert len(store) == 0


def test_loads_legacy_url_to_timestamp_format(tmp_path):
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"https://a.com/1": 1000}), encoding="utf-8")
    store = ArticleStateStore(str(path))
    assert store.is_seen("https://a.com/1")
    assert store._state["https://a.com/1"].first_seen_at == 1000


def test_mark_article_persists_metadata(tmp_path):
    path = str(tmp_path / "state.json")
    store = ArticleStateStore(path)
    article = _article()
    store.mark_article(article, 2000)
    store.save()

    reloaded = ArticleStateStore(path)
    record = reloaded._state[article.url]
    assert record.title == article.title
    assert record.source_name == article.source_name
    assert record.category == article.category
    assert record.published_ts == article.published_ts


def test_expire_removes_old_entries(tmp_path):
    store = ArticleStateStore(str(tmp_path / "state.json"))
    now = int(time.time())
    store.mark_seen("https://a.com/old", now - 40 * 86400)  # 40天前
    store.mark_seen("https://a.com/new", now - 5 * 86400)   # 5天前
    removed = store.expire(max_age_days=30)
    assert removed == 1
    assert not store.is_seen("https://a.com/old")
    assert store.is_seen("https://a.com/new")


def test_expire_zero_does_nothing(tmp_path):
    store = ArticleStateStore(str(tmp_path / "state.json"))
    store.mark_seen("https://a.com/1", 1)
    removed = store.expire(max_age_days=0)
    assert removed == 0
    assert len(store) == 1


def test_save_creates_parent_dirs(tmp_path):
    path = str(tmp_path / "deep" / "nested" / "state.json")
    store = ArticleStateStore(path)
    store.mark_seen("https://a.com/1", 1000)
    store.save()
    assert (tmp_path / "deep" / "nested" / "state.json").exists()
