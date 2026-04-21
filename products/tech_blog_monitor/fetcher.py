# -*- coding: utf-8 -*-
"""
Tech Blog Monitor — source 抓取器

从 RSS / GitHub Releases / changelog 源获取最新文章列表（标题、链接、发布时间、摘要）。

Phase 2 改进：
- requests.Session 复用连接
- 重试退避（最多 3 次，指数退避）
- 并发抓取（ThreadPoolExecutor）
- feed 健康状态统计
- 每个 feed 独立 timeout / verify_ssl / headers / enabled
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import feedparser
import requests
from loguru import logger

from products.tech_blog_monitor.config import FeedSource, TechBlogMonitorConfig
from products.tech_blog_monitor.observability import RunContext
from products.tech_blog_monitor.source_adapters import (
    ChangelogAdapter,
    GitHubReleasesAdapter,
    RssSourceAdapter,
    SourceAdapter,
)

_CST = timezone(timedelta(hours=8))
_MAX_RETRIES = 3
_BACKOFF_BASE = 1.5  # 退避基数（秒）


@dataclass
class Article:
    title: str
    url: str
    source_name: str
    category: str
    source_id: str                    # "{source_name}::{url}" 稳定唯一标识
    rss_summary: str                  # RSS 原始摘要（已去 HTML）
    published: Optional[datetime]     # 带时区的发布时间（CST）
    published_ts: Optional[int]       # UTC Unix 时间戳，便于序列化/比较
    fetched_at: int                   # 抓取时刻 UTC Unix 时间戳
    source_type: str = field(default="rss")
    ai_summary: str = field(default="")  # AI 生成的中文摘要
    content_status: str = field(default="not_fetched")
    content_source: str = field(default="")
    raw_html: str = field(default="")
    clean_text: str = field(default="")
    content_error: str = field(default="")
    content_http_status: Optional[int] = field(default=None)
    content_fetched_at: Optional[int] = field(default=None)
    content_final_url: str = field(default="")
    one_line_summary: str = field(default="")
    key_points: List[str] = field(default_factory=list)
    why_it_matters: str = field(default="")
    recommended_for: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    topic: str = field(default="")
    enrichment_status: str = field(default="not_enriched")
    enrichment_error: str = field(default="")
    relevance_score: float = field(default=0.0)
    relevance_level: str = field(default="not_evaluated")
    relevance_reasons: List[str] = field(default_factory=list)
    matched_signals: List[dict] = field(default_factory=list)
    dependency_match_score: float = field(default=0.0)
    topic_match_score: float = field(default=0.0)
    source_priority_score: float = field(default=0.0)


@dataclass
class FeedHealth:
    """单个 feed 的抓取健康状态。"""
    name: str
    url: str
    success: bool
    article_count: int = 0
    error: str = ""
    retries: int = 0
    source_type: str = "rss"


def _parse_published(entry) -> Optional[datetime]:
    t = entry.get("published_parsed") or entry.get("updated_parsed")
    if not t:
        return None
    try:
        return datetime(*t[:6], tzinfo=timezone.utc).astimezone(_CST)
    except Exception:
        return None


def _strip_html(text: str) -> str:
    import re
    return re.sub(r"<[^>]+>", "", text).strip()


def _passes_keyword_filter(article: Article, keyword_filters: dict) -> bool:
    """
    关键词白名单过滤。

    - 先查分类专属过滤规则，再查全局规则 "*"
    - 规则列表为空表示该分类不过滤（全部通过）
    - 匹配范围：标题 + rss_summary，大小写不敏感
    """
    rules = keyword_filters.get(article.category) or keyword_filters.get("*") or []
    if not rules:
        return True
    text = (article.title + " " + article.rss_summary).lower()
    return any(kw.lower() in text for kw in rules)


def _fetch_rss_source(
    source: FeedSource,
    max_articles: int,
    session: Optional[requests.Session] = None,
) -> Tuple[List[Article], FeedHealth]:
    """
    抓取单个 RSS 源，返回 (文章列表, 健康状态)。

    支持重试退避，使用传入的 Session 复用连接。
    """
    if not source.enabled:
        logger.debug(f"跳过已禁用源: {source.name}")
        return [], FeedHealth(name=source.name, url=source.url, success=False,
                              error="disabled", source_type=source.source_type)

    requester = session or requests
    headers = {"User-Agent": "Mozilla/5.0", **source.headers}
    last_error = ""
    retries = 0

    for attempt in range(_MAX_RETRIES):
        try:
            resp = requester.get(
                source.url,
                timeout=source.timeout,
                headers=headers,
                verify=source.verify_ssl,
            )
            resp.raise_for_status()
            feed = feedparser.parse(resp.content)
            break
        except Exception as e:
            last_error = str(e)
            retries = attempt + 1
            if attempt < _MAX_RETRIES - 1:
                wait = _BACKOFF_BASE ** attempt
                logger.warning(f"抓取失败 {source.name}（第{retries}次），{wait:.1f}s 后重试: {e}")
                time.sleep(wait)
            else:
                logger.warning(f"抓取失败 {source.name}（已重试{retries}次）: {e}")
                return [], FeedHealth(name=source.name, url=source.url, success=False,
                                      error=last_error, retries=retries, source_type=source.source_type)

    fetch_ts = int(datetime.now(timezone.utc).timestamp())
    articles = []
    for entry in feed.entries[:max_articles]:
        title = entry.get("title", "").strip()
        url = entry.get("link", "").strip()
        if not title or not url:
            continue

        raw_summary = (
            entry.get("summary")
            or entry.get("description")
            or entry.get("content", [{}])[0].get("value", "")
        )
        rss_summary = _strip_html(raw_summary)[:500]
        published = _parse_published(entry)
        published_ts = int(published.astimezone(timezone.utc).timestamp()) if published else None

        articles.append(Article(
            title=title,
            url=url,
            source_name=source.name,
            source_type=source.source_type,
            category=source.category,
            source_id=f"{source.name}::{url}",
            rss_summary=rss_summary,
            published=published,
            published_ts=published_ts,
            fetched_at=fetch_ts,
        ))

    health = FeedHealth(name=source.name, url=source.url, success=True,
                        article_count=len(articles), retries=retries, source_type=source.source_type)
    logger.info(f"  {source.name}: {len(articles)} 篇" + (f"（重试{retries}次）" if retries else ""))
    return articles, health


def get_default_source_adapters() -> dict[str, SourceAdapter]:
    return {
        "changelog": ChangelogAdapter(),
        "github_releases": GitHubReleasesAdapter(),
        "rss": RssSourceAdapter(fetch_rss_source=_fetch_rss_source),
    }


def resolve_source_adapter(
    source: FeedSource,
    *,
    adapters: dict[str, SourceAdapter] | None = None,
) -> SourceAdapter:
    resolved_adapters = adapters or get_default_source_adapters()
    adapter = resolved_adapters.get(source.source_type)
    if adapter is None:
        raise ValueError(f"unsupported source_type: {source.source_type}")
    return adapter


def fetch_source(
    source: FeedSource,
    max_articles: int,
    session: Optional[requests.Session] = None,
    *,
    adapters: dict[str, SourceAdapter] | None = None,
) -> Tuple[List[Article], FeedHealth]:
    adapter = resolve_source_adapter(source, adapters=adapters)
    return adapter.fetch(
        source,
        max_articles=max_articles,
        session=session,
    )


def fetch_feed(
    source: FeedSource,
    max_articles: int,
    session: Optional[requests.Session] = None,
) -> Tuple[List[Article], FeedHealth]:
    """
    RSS 兼容 facade。

    保留旧调用路径，但内部统一经 adapter 层执行。
    """
    return fetch_source(source, max_articles, session=session)


def _fetch_feed_with_observability(
    source: FeedSource,
    *,
    max_articles: int,
    session: requests.Session,
    run_context: RunContext | None,
    adapters: dict[str, SourceAdapter] | None,
) -> Tuple[List[Article], FeedHealth]:
    task = None
    if run_context is not None:
        task = run_context.start_task(
            task_id=f"{run_context.run_id}:source:{source.source_type}:{source.name}",
            task_type="fetch_feed",
            dimensions={
                "source_name": source.name,
                "feed_url": source.url,
                "category": source.category,
                "source_type": source.source_type,
            },
        )

    try:
        articles, health = fetch_source(
            source,
            max_articles,
            session=session,
            adapters=adapters,
        )
    except Exception as exc:
        if task is not None:
            task.complete(
                status="failed",
                error_code=exc.__class__.__name__,
                error_message=str(exc),
            )
        raise

    if task is not None:
        task.complete(
            status="success" if health.success else "failed",
            error_message=health.error,
            dimensions={
                "article_count": health.article_count,
                "retries": health.retries,
                "success": health.success,
                "source_type": health.source_type,
            },
        )
    return articles, health


def fetch_all(
    config: TechBlogMonitorConfig,
    *,
    run_context: RunContext | None = None,
    adapters: dict[str, SourceAdapter] | None = None,
) -> Tuple[List[Article], List[FeedHealth]]:
    """
    并发抓取所有 source，过滤、去重、排序后返回 (文章列表, 健康状态列表)。
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=config.max_age_days) if config.max_age_days > 0 else None

    enabled_feeds = [f for f in config.feeds if f.enabled]
    disabled_feeds = [f for f in config.feeds if not f.enabled]

    health_list: List[FeedHealth] = [
        FeedHealth(name=f.name, url=f.url, success=False, error="disabled", source_type=f.source_type)
        for f in disabled_feeds
    ]

    resolved_adapters = adapters or get_default_source_adapters()
    session = requests.Session()
    raw_results: Dict[tuple[str, str], Tuple[List[Article], FeedHealth]] = {}

    logger.info(f"并发抓取 {len(enabled_feeds)} 个源（workers={config.fetch_workers}）")

    with ThreadPoolExecutor(max_workers=config.fetch_workers) as executor:
        future_to_source = {
            executor.submit(
                _fetch_feed_with_observability,
                source,
                max_articles=config.max_articles_per_feed,
                session=session,
                run_context=run_context,
                adapters=resolved_adapters,
            ): source
            for source in enabled_feeds
        }
        for future in as_completed(future_to_source):
            source = future_to_source[future]
            try:
                articles, health = future.result()
                raw_results[(source.source_type, source.name)] = (articles, health)
            except Exception as e:
                logger.error(f"未预期错误 {source.name}: {e}")
                raw_results[(source.source_type, source.name)] = ([], FeedHealth(
                    name=source.name, url=source.url, success=False, error=str(e), source_type=source.source_type
                ))

    session.close()

    # 按原始 feed 顺序收集健康状态和文章
    all_articles: List[Article] = []
    seen_urls: set = set()

    for source in enabled_feeds:
        articles, health = raw_results.get((source.source_type, source.name), ([], FeedHealth(
            name=source.name, url=source.url, success=False, error="no result", source_type=source.source_type
        )))
        health_list.append(health)

        if not articles:
            continue

        # 时效过滤
        if cutoff:
            articles = [
                a for a in articles
                if a.published is None or a.published.astimezone(timezone.utc) >= cutoff
            ]

        # 关键词过滤
        if config.keyword_filters:
            articles = [a for a in articles if _passes_keyword_filter(a, config.keyword_filters)]

        # URL 去重
        deduped = []
        for a in articles:
            if a.url not in seen_urls:
                seen_urls.add(a.url)
                deduped.append(a)
        articles = deduped

        # 单源上限
        if config.max_articles_per_source > 0:
            articles = articles[: config.max_articles_per_source]

        all_articles.extend(articles)

    # 全局按发布时间降序排序（无时间的排最后）
    all_articles.sort(
        key=lambda a: a.published or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )

    # 总数上限
    if config.max_total_articles > 0:
        all_articles = all_articles[: config.max_total_articles]

    success_count = sum(1 for h in health_list if h.success)
    fail_count = len(health_list) - success_count
    logger.info(
        f"抓取完成: {len(all_articles)} 篇文章，"
        f"{success_count} 个源成功，{fail_count} 个源失败"
    )
    return all_articles, health_list
