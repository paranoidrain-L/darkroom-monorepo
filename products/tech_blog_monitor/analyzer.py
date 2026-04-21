# -*- coding: utf-8 -*-
"""
Tech Blog Monitor — AI 分析器

Phase 3 改进：
- 单篇文章结构化 enrichment
- enrichment schema 校验与部分成功隔离
- backend 可用性检查
- 趋势分析失败降级说明
"""

from __future__ import annotations

import json
import re
from typing import Dict, List, Optional, Tuple

from loguru import logger
from pydantic import BaseModel, Field, ValidationError, field_validator

from products.tech_blog_monitor.fetcher import Article
from runtime.factory import get_client as _get_client

_KNOWN_BACKENDS = {"claude", "claude_code", "trae", "codex"}

_TREND_FALLBACK = (
    "> ⚠️ **趋势分析不可用**：AI 后端调用失败，本次报告跳过趋势分析。"
    "请检查 `AGENT_RUNTIME` 配置或网络连接。"
)

_TREND_PROMPT_TEMPLATE = """\
你是一位技术趋势分析师。以下是本期从多个技术博客抓取的文章标题列表。

请严格按照以下结构输出 Markdown，不要添加额外标题或前言：

## 本期热点主题

（列出 3-5 个热点，每个格式为：**主题名** — 一句话说明）

## 值得关注的技术方向

（列出 2-4 个方向，每个格式为：- **方向名**：说明）

## 一句话总结

（一句话概括本期技术动态）

---

文章标题列表：
{titles}"""


class ArticleEnrichmentModel(BaseModel):
    index: int
    one_line_summary: str = Field(min_length=1)
    key_points: List[str] = Field(min_length=1)
    why_it_matters: str = Field(min_length=1)
    recommended_for: List[str] = Field(min_length=1)
    tags: List[str] = Field(min_length=1)
    topic: str = Field(min_length=1)

    @field_validator(
        "one_line_summary",
        "why_it_matters",
        "topic",
        mode="before",
    )
    @classmethod
    def _strip_string(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("必须是字符串")
        stripped = value.strip()
        if not stripped:
            raise ValueError("不能为空")
        return stripped

    @field_validator("key_points", "recommended_for", "tags", mode="before")
    @classmethod
    def _normalize_string_list(cls, value: object) -> List[str]:
        if not isinstance(value, list):
            raise ValueError("必须是列表")
        result = [item.strip() for item in value if isinstance(item, str) and item.strip()]
        if not result:
            raise ValueError("不能为空列表")
        return result


def check_backend(backend: str) -> Optional[str]:
    if backend not in _KNOWN_BACKENDS:
        return f"未知 AI 后端: {backend!r}，支持的后端: {', '.join(sorted(_KNOWN_BACKENDS))}"
    return None


def _build_enrichment_prompt(articles: List[Article]) -> str:
    lines = [
        "你是一位技术文章分析助手。以下是从多个技术博客抓取的文章。",
        "请为每篇文章输出结构化中文理解结果。",
        "严格按照以下 JSON 数组格式输出，不要添加任何其他内容：",
        (
            '[{"index": 0, "one_line_summary": "...", "key_points": ["..."], '
            '"why_it_matters": "...", "recommended_for": ["..."], "tags": ["..."], '
            '"topic": "..."}]'
        ),
        "",
        "要求：",
        "- `one_line_summary`：一句话总结，30字以内",
        "- `key_points`：1-3 条要点",
        "- `why_it_matters`：说明为什么值得关注",
        "- `recommended_for`：推荐给哪些读者",
        "- `tags`：1-5 个标签",
        "- `topic`：主题归类",
        "",
        "文章列表：",
    ]
    for i, article in enumerate(articles):
        excerpt = article.clean_text[:800] if article.clean_text else article.rss_summary[:200]
        lines.append(f"[{i}] 标题: {article.title}")
        lines.append(f"    来源: {article.source_name}")
        if excerpt:
            lines.append(f"    内容: {excerpt}")
    return "\n".join(lines)


def _build_trend_prompt(articles: List[Article]) -> str:
    titles = "\n".join(f"- [{article.source_name}] {article.title}" for article in articles)
    return _TREND_PROMPT_TEMPLATE.format(titles=titles)


def _extract_json_array(raw: str) -> Tuple[Optional[List[object]], Optional[str]]:
    match = re.search(r"\[.*\]", raw, re.DOTALL)
    if not match:
        return None, f"响应中未找到 JSON 数组（前100字符: {raw[:100]!r}）"
    try:
        data = json.loads(match.group())
    except json.JSONDecodeError as exc:
        return None, f"JSON 解析失败: {exc}（原始片段: {match.group()[:100]!r}）"
    if not isinstance(data, list):
        return None, "JSON 顶层不是数组"
    return data, None


def _parse_enrichments(
    raw: str,
    count: int,
) -> Tuple[Dict[int, ArticleEnrichmentModel], Dict[int, str], Optional[str]]:
    data, fatal_error = _extract_json_array(raw)
    if fatal_error:
        return {}, {}, fatal_error

    enrichments: Dict[int, ArticleEnrichmentModel] = {}
    item_errors: Dict[int, str] = {}
    for item in data or []:
        if not isinstance(item, dict):
            continue
        idx = item.get("index")
        if not isinstance(idx, int) or not (0 <= idx < count):
            continue
        try:
            enrichments[idx] = ArticleEnrichmentModel.model_validate(item)
        except ValidationError as exc:
            item_errors[idx] = exc.errors()[0]["msg"]

    if not enrichments:
        return {}, item_errors, f"enrichment JSON 解析后无有效条目（原始条目数 {len(data or [])}）"
    return enrichments, item_errors, None


def _apply_enrichment(article: Article, enrichment: ArticleEnrichmentModel) -> None:
    article.one_line_summary = enrichment.one_line_summary
    article.ai_summary = enrichment.one_line_summary
    article.key_points = list(enrichment.key_points)
    article.why_it_matters = enrichment.why_it_matters
    article.recommended_for = list(enrichment.recommended_for)
    article.tags = list(enrichment.tags)
    article.topic = enrichment.topic
    article.enrichment_status = "enriched"
    article.enrichment_error = ""


def _mark_articles_failed(articles: List[Article], reason: str) -> None:
    for article in articles:
        article.enrichment_status = "failed"
        article.enrichment_error = reason


def analyze(articles: List[Article], backend: str = "trae") -> Tuple[List[Article], str]:
    if not articles:
        return articles, ""

    backend_error = check_backend(backend)
    if backend_error:
        logger.error(f"AI 后端不可用: {backend_error}")
        _mark_articles_failed(articles, backend_error)
        return articles, _TREND_FALLBACK

    try:
        client = _get_client(backend)
    except Exception as exc:
        reason = f"AI client 初始化失败（backend={backend}）: {exc}"
        logger.warning(reason)
        _mark_articles_failed(articles, str(exc))
        return articles, _TREND_FALLBACK

    logger.info(f"生成 {len(articles)} 篇文章结构化 enrichment（backend={backend}）...")
    enrichment_prompt = _build_enrichment_prompt(articles)
    try:
        raw = client.chat(enrichment_prompt)
        enrichments, item_errors, fatal_error = _parse_enrichments(raw, len(articles))
        if fatal_error:
            logger.warning(f"enrichment 解析失败: {fatal_error}")
            _mark_articles_failed(articles, fatal_error)
        else:
            filled = 0
            for index, article in enumerate(articles):
                enrichment = enrichments.get(index)
                if enrichment is not None:
                    _apply_enrichment(article, enrichment)
                    filled += 1
                else:
                    article.enrichment_status = "failed"
                    article.enrichment_error = item_errors.get(index, "缺少该文章的 enrichment 条目")
            logger.info(f"enrichment 填充完成: {filled}/{len(articles)} 篇")
            if item_errors:
                logger.warning(f"enrichment 部分条目校验失败: {item_errors}")
    except Exception as exc:
        reason = f"enrichment 调用失败（backend={backend}）: {exc}"
        logger.warning(reason)
        _mark_articles_failed(articles, str(exc))

    logger.info("生成技术趋势分析...")
    trend_prompt = _build_trend_prompt(articles)
    trend_md = ""
    try:
        trend_md = client.chat(trend_prompt).strip()
        if not trend_md:
            logger.warning("趋势分析返回空响应，使用降级说明")
            trend_md = _TREND_FALLBACK
    except Exception as exc:
        logger.warning(f"趋势分析失败（backend={backend}）: {exc}")
        trend_md = _TREND_FALLBACK

    return articles, trend_md
