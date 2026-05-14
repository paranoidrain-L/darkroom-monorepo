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
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from loguru import logger
from pydantic import BaseModel, Field, ValidationError, field_validator

from products.tech_blog_monitor.fetcher import Article
from runtime.factory import get_client as _get_client

_KNOWN_BACKENDS = {"claude", "claude_code", "trae", "codex"}
_ENRICHMENT_BATCH_SIZE = 5
_DEFAULT_ENRICHMENT_WORKERS = 1
_DEFAULT_ENRICHMENT_CONTENT_CHARS = 4000
_DEFAULT_ENRICHMENT_SUMMARY_CHARS = 300

_TREND_FALLBACK = (
    "> ⚠️ **趋势分析不可用**：AI 后端调用失败，本次报告跳过趋势分析。" "请检查 `AGENT_RUNTIME` 配置或网络连接。"
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
    detailed_summary: str = Field(default="")
    key_points: List[str] = Field(min_length=1)
    why_it_matters: str = Field(min_length=1)
    recommended_for: List[str] = Field(min_length=1)
    tags: List[str] = Field(min_length=1)
    topic: str = Field(min_length=1)

    @field_validator(
        "one_line_summary",
        "detailed_summary",
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
        "请为每篇文章输出结构化中文理解结果，重点提炼技术机制、关键变化、适用场景、工程影响与潜在约束。",
        "你的语气应该像一位认真读完文章后的技术负责人或资深工程师，评价要全面、自然、有判断，不要写成模板腔。",
        "严格按照以下 JSON 数组格式输出，不要添加任何其他内容：",
        (
            '[{"index": 0, "one_line_summary": "...", "detailed_summary": "...", "key_points": ["..."], '
            '"why_it_matters": "...", "recommended_for": ["..."], "tags": ["..."], '
            '"topic": "..."}]'
        ),
        "",
        "要求：",
        "- `one_line_summary`：一句话总结，尽量控制在 20-35 个汉字，直接点出“做了什么变化/发布了什么能力”",
        "- `detailed_summary`：2-4 句中文摘要，尽量覆盖技术对象、核心机制、变化点和落地场景，不要空话，不要重复标题",
        "- `key_points`：4-6 条要点，覆盖机制、变化、边界、性能/架构影响、使用前提等不同维度；其中至少 1 条必须以 `限制点评：` 开头，写成完整自然句，明确指出限制、风险、迁移成本、适用边界或证据不足",
        "- `why_it_matters`：1-2 句自然中文评论，直接评价“这篇文章最值得关注的价值是什么、会影响谁的什么决策”；不要只写“值得关注”“有参考价值”这类空泛结论",
        "- `recommended_for`：1-3 类读者，使用角色或团队视角，比如“平台工程师”“Agent 应用开发者”",
        "- `tags`：3-6 个标签，优先技术名词、产品名、协议名、能力名，不要太泛",
        "- `topic`：主题归类，尽量使用稳定、可复用的主题词",
        "",
        "补充约束：",
        "- 输出必须忠于提供的标题、摘要和正文内容，不要编造未出现的功能、指标或结论",
        "- 如果文章是版本发布、产品公告或架构实践，请明确写出“新增/改进/发布/迁移/治理”等变化类型",
        "- 如果文章包含明显限制、前提条件、适用范围或 trade-off，请优先写进 `key_points` 里的 `限制点评：...`",
        "- `key_points` 不要重复改写同一句话，要覆盖不同维度的信息；`限制点评：...` 不要写成套话，要落到具体对象、条件或风险",
        "- `why_it_matters` 和 `限制点评：...` 都要像人类读后评论，允许带判断，但判断必须能从提供内容中推出",
        "- 全部字段都用中文输出；保留必要英文术语、产品名、协议名即可",
        "",
        "文章列表：",
    ]
    for i, article in enumerate(articles):
        content = _article_analysis_content(article)
        lines.append(f"[{i}] 标题: {article.title}")
        lines.append(f"    来源: {article.source_name}")
        if article.category:
            lines.append(f"    分类: {article.category}")
        if article.published_ts is not None:
            lines.append(f"    发布时间戳: {article.published_ts}")
        if article.rss_summary:
            lines.append(f"    RSS 摘要: {article.rss_summary[:_DEFAULT_ENRICHMENT_SUMMARY_CHARS]}")
        if content:
            lines.append(f"    正文内容: {content}")
    return "\n".join(lines)


def _resolve_enrichment_content_chars() -> int:
    raw = os.environ.get("TECH_BLOG_ENRICHMENT_CONTENT_CHARS")
    if raw is None or not raw.strip():
        return _DEFAULT_ENRICHMENT_CONTENT_CHARS
    try:
        value = int(raw)
    except ValueError:
        logger.warning(
            "TECH_BLOG_ENRICHMENT_CONTENT_CHARS={} 不是合法整数，使用默认值 {}",
            raw,
            _DEFAULT_ENRICHMENT_CONTENT_CHARS,
        )
        return _DEFAULT_ENRICHMENT_CONTENT_CHARS
    if value < 0:
        logger.warning(
            "TECH_BLOG_ENRICHMENT_CONTENT_CHARS={} 小于 0，使用默认值 {}",
            raw,
            _DEFAULT_ENRICHMENT_CONTENT_CHARS,
        )
        return _DEFAULT_ENRICHMENT_CONTENT_CHARS
    return value


def _article_analysis_content(article: Article) -> str:
    if article.clean_text:
        limit = _resolve_enrichment_content_chars()
        if limit == 0:
            return article.clean_text
        return article.clean_text[:limit]
    return article.rss_summary[:_DEFAULT_ENRICHMENT_SUMMARY_CHARS]


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
    article.ai_summary = enrichment.detailed_summary or enrichment.one_line_summary
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


def _enrichment_batches(articles: List[Article], batch_size: int | None = None) -> List[List[Article]]:
    size = max(1, batch_size or _ENRICHMENT_BATCH_SIZE)
    return [articles[start : start + size] for start in range(0, len(articles), size)]  # noqa: E203


def _resolve_enrichment_workers() -> int:
    raw = os.environ.get("TECH_BLOG_ENRICHMENT_WORKERS")
    if raw is None or not raw.strip():
        return _DEFAULT_ENRICHMENT_WORKERS
    try:
        workers = int(raw)
    except ValueError:
        logger.warning(
            "TECH_BLOG_ENRICHMENT_WORKERS={} 不是合法整数，使用默认值 {}",
            raw,
            _DEFAULT_ENRICHMENT_WORKERS,
        )
        return _DEFAULT_ENRICHMENT_WORKERS
    if workers < 1:
        logger.warning(
            "TECH_BLOG_ENRICHMENT_WORKERS={} 小于 1，使用默认值 {}",
            raw,
            _DEFAULT_ENRICHMENT_WORKERS,
        )
        return _DEFAULT_ENRICHMENT_WORKERS
    return workers


@dataclass
class _EnrichmentBatchResult:
    batch_index: int
    total_batches: int
    batch_articles: List[Article]
    enrichments: Dict[int, ArticleEnrichmentModel]
    item_errors: Dict[int, str]
    fatal_error: Optional[str] = None
    call_error: Optional[str] = None


def _run_enrichment_batch(
    *,
    client,
    backend: str,
    batch_index: int,
    total_batches: int,
    batch_articles: List[Article],
) -> _EnrichmentBatchResult:
    logger.info(f"enrichment 批次 {batch_index}/{total_batches}（{len(batch_articles)} 篇，backend={backend}）...")
    enrichment_prompt = _build_enrichment_prompt(batch_articles)
    try:
        raw = client.chat(enrichment_prompt)
        enrichments, item_errors, fatal_error = _parse_enrichments(raw, len(batch_articles))
        return _EnrichmentBatchResult(
            batch_index=batch_index,
            total_batches=total_batches,
            batch_articles=batch_articles,
            enrichments=enrichments,
            item_errors=item_errors,
            fatal_error=fatal_error,
        )
    except Exception as exc:
        return _EnrichmentBatchResult(
            batch_index=batch_index,
            total_batches=total_batches,
            batch_articles=batch_articles,
            enrichments={},
            item_errors={},
            call_error=str(exc),
        )


def _apply_enrichment_batch_result(result: _EnrichmentBatchResult, *, backend: str) -> int:
    if result.call_error:
        reason = f"enrichment 调用失败（backend={backend}）: {result.call_error}"
        logger.warning(reason)
        _mark_articles_failed(result.batch_articles, result.call_error)
        return 0

    if result.fatal_error:
        logger.warning(f"enrichment 批次 {result.batch_index} 解析失败: {result.fatal_error}")
        _mark_articles_failed(result.batch_articles, result.fatal_error)
        return 0

    filled = 0
    for index, article in enumerate(result.batch_articles):
        enrichment = result.enrichments.get(index)
        if enrichment is not None:
            _apply_enrichment(article, enrichment)
            filled += 1
        else:
            article.enrichment_status = "failed"
            article.enrichment_error = result.item_errors.get(index, "缺少该文章的 enrichment 条目")
    if result.item_errors:
        logger.warning(f"enrichment 批次 {result.batch_index} 部分条目校验失败: {result.item_errors}")
    return filled


def _run_enrichment_batches(
    *,
    client,
    backend: str,
    batches: List[List[Article]],
    workers: int,
) -> int:
    if not batches:
        return 0

    if workers <= 1 or len(batches) == 1:
        filled = 0
        for batch_index, batch_articles in enumerate(batches, start=1):
            result = _run_enrichment_batch(
                client=client,
                backend=backend,
                batch_index=batch_index,
                total_batches=len(batches),
                batch_articles=batch_articles,
            )
            filled += _apply_enrichment_batch_result(result, backend=backend)
        return filled

    effective_workers = min(workers, len(batches))
    logger.info("并发执行 enrichment 批次：workers={} batches={}", effective_workers, len(batches))
    filled = 0
    with ThreadPoolExecutor(max_workers=effective_workers) as executor:
        futures = [
            executor.submit(
                _run_enrichment_batch,
                client=client,
                backend=backend,
                batch_index=batch_index,
                total_batches=len(batches),
                batch_articles=batch_articles,
            )
            for batch_index, batch_articles in enumerate(batches, start=1)
        ]
        for future in as_completed(futures):
            filled += _apply_enrichment_batch_result(future.result(), backend=backend)
    return filled


def analyze(articles: List[Article], backend: str = "codex") -> Tuple[List[Article], str]:
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
    batches = _enrichment_batches(articles)
    filled = _run_enrichment_batches(
        client=client,
        backend=backend,
        batches=batches,
        workers=_resolve_enrichment_workers(),
    )
    logger.info(f"enrichment 填充完成: {filled}/{len(articles)} 篇")

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
