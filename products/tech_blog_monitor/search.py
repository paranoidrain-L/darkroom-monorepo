# -*- coding: utf-8 -*-
"""Tech Blog Monitor — Phase 4 检索接口。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from time import perf_counter
from typing import List, Optional

from products.tech_blog_monitor.observability.metrics import get_default_metrics_registry
from products.tech_blog_monitor.repository_provider import open_repository_bundle


@dataclass
class SearchQuery:
    query: str = ""
    source_name: str = ""
    category: str = ""
    topic: str = ""
    tag: str = ""
    days: int = 0
    limit: int = 20


def _published_from_days(days: int) -> Optional[int]:
    if days <= 0:
        return None
    now = datetime.now(timezone.utc)
    return int(now.timestamp()) - days * 86400


def search_articles(db_path: str, query: SearchQuery, *, database_url: str = "") -> List[dict]:
    started = perf_counter()
    status = "success"
    published_from_ts = _published_from_days(query.days)
    try:
        with open_repository_bundle(asset_db_path=db_path, database_url=database_url) as bundle:
            return bundle.search_repository.search_articles(
                query=query.query,
                source_name=query.source_name or None,
                category=query.category or None,
                topic=query.topic or None,
                tag=query.tag or None,
                published_from_ts=published_from_ts,
                limit=query.limit,
            )
    except Exception:
        status = "failed"
        raise
    finally:
        get_default_metrics_registry().observe_search_latency(
            (perf_counter() - started) * 1000,
            dimensions={
                "status": status,
                "has_query": bool(query.query),
                "has_database_url": bool(database_url),
            },
        )


def format_search_results(results: List[dict]) -> str:
    if not results:
        return "未找到匹配文章。"

    lines: List[str] = []
    for index, item in enumerate(results, start=1):
        parts = [f"{index}. {item['title']}"]
        meta = [item.get("source_name", "")]
        if item.get("topic"):
            meta.append(item["topic"])
        if item.get("published_ts"):
            dt = datetime.fromtimestamp(item["published_ts"], tz=timezone.utc)
            meta.append(dt.strftime("%Y-%m-%d"))
        meta_text = " | ".join(part for part in meta if part)
        if meta_text:
            parts.append(f"   {meta_text}")

        summary = item.get("one_line_summary") or item.get("ai_summary") or item.get("rss_summary", "")
        if summary:
            parts.append(f"   {summary}")

        tags = item.get("tags") or []
        if tags:
            parts.append(f"   tags: {', '.join(tags)}")

        parts.append(f"   {item['url']}")
        lines.extend(parts)

    return "\n".join(lines)
