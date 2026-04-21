# -*- coding: utf-8 -*-
"""
Tech Blog Monitor — 增量状态存储

维护 seen_articles.json，记录已处理过的文章 URL 及其元数据。
用于区分"本次新增"与"历史已见"，并为历史归档提供基础状态。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, Optional, Set, Tuple

from products.tech_blog_monitor.fetcher import Article

_UTC = timezone.utc
_STATE_VERSION = 2


@dataclass
class SeenArticleRecord:
    first_seen_at: int
    last_seen_at: int
    title: str = ""
    source_name: str = ""
    category: str = ""
    published_ts: Optional[int] = None

    @classmethod
    def from_json_value(cls, value: object) -> Optional["SeenArticleRecord"]:
        if isinstance(value, int):
            return cls(first_seen_at=value, last_seen_at=value)
        if not isinstance(value, dict):
            return None

        first_seen_at = value.get("first_seen_at")
        last_seen_at = value.get("last_seen_at", first_seen_at)
        if not isinstance(first_seen_at, int) or not isinstance(last_seen_at, int):
            return None

        published_ts = value.get("published_ts")
        if not isinstance(published_ts, int):
            published_ts = None

        return cls(
            first_seen_at=first_seen_at,
            last_seen_at=last_seen_at,
            title=value.get("title", "") if isinstance(value.get("title"), str) else "",
            source_name=value.get("source_name", "") if isinstance(value.get("source_name"), str) else "",
            category=value.get("category", "") if isinstance(value.get("category"), str) else "",
            published_ts=published_ts,
        )

    def to_json_value(self) -> dict:
        return {
            "first_seen_at": self.first_seen_at,
            "last_seen_at": self.last_seen_at,
            "title": self.title,
            "source_name": self.source_name,
            "category": self.category,
            "published_ts": self.published_ts,
        }


class ArticleStateStore:
    """
    持久化已见文章状态。

    支持兼容旧格式：
    {
        "https://example.com/post": 1744243200
    }

    当前格式：
    {
        "version": 2,
        "articles": {
            "https://example.com/post": {
                "first_seen_at": 1744243200,
                "last_seen_at": 1744243200,
                "title": "Example",
                "source_name": "Example Feed",
                "category": "行业风向标",
                "published_ts": 1744200000
            }
        }
    }
    """

    def __init__(self, path: str) -> None:
        self._path = Path(path)
        self._state: Dict[str, SeenArticleRecord] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            self._state = {}
            return

        raw_articles = data.get("articles") if isinstance(data, dict) and "articles" in data else data
        if not isinstance(raw_articles, dict):
            self._state = {}
            return

        state: Dict[str, SeenArticleRecord] = {}
        for url, value in raw_articles.items():
            if not isinstance(url, str):
                continue
            record = SeenArticleRecord.from_json_value(value)
            if record is not None:
                state[url] = record
        self._state = state

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": _STATE_VERSION,
            "articles": {url: record.to_json_value() for url, record in sorted(self._state.items())},
        }
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    def is_seen(self, url: str) -> bool:
        return url in self._state

    def mark_seen(self, url: str, ts: int) -> None:
        record = self._state.get(url)
        if record is None:
            self._state[url] = SeenArticleRecord(first_seen_at=ts, last_seen_at=ts)
            return
        record.last_seen_at = max(record.last_seen_at, ts)

    def mark_article(self, article: Article, ts: int) -> None:
        record = self._state.get(article.url)
        if record is None:
            self._state[article.url] = SeenArticleRecord(
                first_seen_at=ts,
                last_seen_at=ts,
                title=article.title,
                source_name=article.source_name,
                category=article.category,
                published_ts=article.published_ts,
            )
            return

        record.last_seen_at = max(record.last_seen_at, ts)
        if article.title:
            record.title = article.title
        if article.source_name:
            record.source_name = article.source_name
        if article.category:
            record.category = article.category
        if article.published_ts is not None:
            record.published_ts = article.published_ts

    def new_urls(self, urls: Set[str]) -> Set[str]:
        """返回 urls 中尚未见过的子集。"""
        return {u for u in urls if u not in self._state}

    def items(self) -> Iterable[Tuple[str, SeenArticleRecord]]:
        return self._state.items()

    def expire(self, max_age_days: int) -> int:
        """删除超过 max_age_days 天未出现的条目，返回删除数量。"""
        if max_age_days <= 0:
            return 0
        cutoff = int((datetime.now(_UTC) - timedelta(days=max_age_days)).timestamp())
        before = len(self._state)
        self._state = {
            url: record
            for url, record in self._state.items()
            if record.last_seen_at >= cutoff
        }
        return before - len(self._state)

    def __len__(self) -> int:
        return len(self._state)
