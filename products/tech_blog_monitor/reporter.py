# -*- coding: utf-8 -*-
"""
Tech Blog Monitor — 报告渲染器

Phase 3 改进：
- 去除 trend_md 中重复的"技术趋势分析"标题
- 清理 AI 摘要尾部空行和多余 > 块引用
- 支持 view="by_category"（默认）和 view="by_time" 两种展示方式
- 支持 new_urls 参数，在报告中区分"本次新增"与"全部文章"
- 抓取状态摘要（Phase 2 已有，保留）
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Literal, Optional, Set

from products.tech_blog_monitor.fetcher import Article, FeedHealth
from products.tech_blog_monitor.internal_relevance.models import RelevanceReport
from products.tech_blog_monitor.internal_relevance.report import build_markdown_summary

_CST = timezone(timedelta(hours=8))

ViewMode = Literal["by_category", "by_time"]
IncrementalMode = Literal["split", "new_only"]

# AI 返回的 trend_md 可能自带趋势分析标题，需要去除避免嵌套重复
# 匹配任何以"技术趋势"或"趋势分析"开头的标题行（含"报告"等后缀变体）
_TREND_HEADING_RE = re.compile(
    r"^#{1,3}\s*(技术趋势|趋势分析|Trend\s*Analysis)[^\n]*$",
    re.MULTILINE | re.IGNORECASE,
)


def _clean_trend_md(trend_md: str) -> str:
    """去除 trend_md 中重复的顶层标题行。"""
    return _TREND_HEADING_RE.sub("", trend_md).strip()


def _clean_ai_summary(text: str) -> str:
    """清理 AI 摘要：去除尾部空白行和多余的 > 块引用前缀。"""
    # 去除每行开头多余的 "> " 前缀（AI 有时会在摘要里加引用格式）
    lines = [re.sub(r"^>\s*", "", line) for line in text.splitlines()]
    # 去除尾部空行
    while lines and not lines[-1].strip():
        lines.pop()
    return " ".join(lines).strip()


def _render_article(a: Article, is_new: bool = False) -> List[str]:
    """渲染单篇文章为 Markdown 行列表。"""
    pub_str = a.published.strftime("%m-%d") if a.published else ""
    new_badge = " 🆕" if is_new else ""
    title_line = f"- **[{a.title}]({a.url})**{new_badge}"
    if pub_str:
        title_line += f" `{pub_str}`"
    title_line += f" — *{a.source_name}*"

    lines = [title_line]
    raw_summary = _clean_ai_summary(a.ai_summary) if a.ai_summary else a.rss_summary[:100]
    if raw_summary:
        lines.append(f"  > {raw_summary}")
    lines.append("")
    return lines


def _render_by_category(articles: List[Article], new_urls: Set[str]) -> List[str]:
    groups: Dict[str, List[Article]] = defaultdict(list)
    for a in articles:
        groups[a.category].append(a)

    lines: List[str] = []
    for category, cat_articles in groups.items():
        lines += [f"### {category}（{len(cat_articles)} 篇）", ""]
        for a in cat_articles:
            lines += _render_article(a, is_new=a.url in new_urls)
    return lines


def _render_by_time(articles: List[Article], new_urls: Set[str]) -> List[str]:
    """按发布时间降序，无日期的排最后。"""
    sorted_articles = sorted(
        articles,
        key=lambda a: a.published or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    lines: List[str] = []
    for a in sorted_articles:
        lines += _render_article(a, is_new=a.url in new_urls)
    return lines


def build_report(
    articles: List[Article],
    trend_md: str,
    health_list: Optional[List[FeedHealth]] = None,
    new_urls: Optional[Set[str]] = None,
    view: ViewMode = "by_category",
    incremental_mode: IncrementalMode = "split",
    relevance_report: RelevanceReport | None = None,
) -> str:
    now = datetime.now(_CST)
    has_incremental = new_urls is not None
    new_urls = new_urls or set()
    new_count = sum(1 for a in articles if a.url in new_urls)

    header_parts = [
        f"**生成时间**: {now.strftime('%Y-%m-%d %H:%M')} (CST)",
        f"**文章总数**: {len(articles)} 篇，来自 {len({a.source_name for a in articles})} 个博客",
    ]
    if has_incremental:
        header_parts.append(f"**本次新增**: {new_count} 篇")

    lines: List[str] = ["# 技术博客阅读报告", ""]
    lines += header_parts
    lines.append("")

    # 趋势分析
    if trend_md:
        cleaned = _clean_trend_md(trend_md)
        if cleaned:
            lines += ["## 技术趋势分析", "", cleaned, ""]

    if relevance_report is not None:
        lines += build_markdown_summary(relevance_report)

    # 文章列表
    if incremental_mode == "new_only" and has_incremental:
        lines += [f"## 本次新增（{new_count} 篇）", ""]
        if articles:
            lines += (_render_by_category(articles, new_urls) if view == "by_category"
                      else _render_by_time(articles, new_urls))
        else:
            lines += ["本次无新增文章。", ""]
    elif new_urls and new_count < len(articles):
        # 有增量信息时，先输出新增视图，再输出全部
        new_articles = [a for a in articles if a.url in new_urls]

        lines += [f"## 本次新增（{new_count} 篇）", ""]
        lines += (_render_by_category(new_articles, new_urls) if view == "by_category"
                  else _render_by_time(new_articles, new_urls))

        lines += [f"## 全部文章（{len(articles)} 篇）", ""]
        lines += (_render_by_category(articles, new_urls) if view == "by_category"
                  else _render_by_time(articles, new_urls))
    else:
        lines += [f"## 文章列表（{len(articles)} 篇）", ""]
        lines += (_render_by_category(articles, new_urls) if view == "by_category"
                  else _render_by_time(articles, new_urls))

    # Feed 抓取状态摘要
    if health_list:
        lines += _build_health_section(health_list)

    return "\n".join(lines)


def _build_health_section(health_list: List[FeedHealth]) -> List[str]:
    success = [h for h in health_list if h.success]
    failed = [h for h in health_list if not h.success]

    lines = [
        "## Feed 抓取状态",
        "",
        f"成功 {len(success)} 个 / 失败 {len(failed)} 个 / 共 {len(health_list)} 个",
        "",
    ]

    if failed:
        lines += ["**失败源：**", ""]
        for h in failed:
            reason = h.error or "unknown"
            lines.append(f"- ❌ **{h.name}** — `{reason}`")
        lines.append("")

    lines += ["**成功源：**", ""]
    for h in success:
        retry_note = f"（重试{h.retries}次）" if h.retries else ""
        lines.append(f"- ✅ {h.name} — {h.article_count} 篇{retry_note}")
    lines.append("")

    return lines
