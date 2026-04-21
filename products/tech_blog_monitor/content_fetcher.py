# -*- coding: utf-8 -*-
"""
Tech Blog Monitor — 正文抓取与正文清洗

Modernization P1.5:
- Trafilatura 作为主抽取路径
- heuristic extractor 作为 fallback
- 质量门禁避免噪声正文静默成功
- Playwright 仅在必要时进入受控兜底
"""

from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from threading import BoundedSemaphore, Lock
from typing import Callable, Optional

import requests
from loguru import logger

from products.tech_blog_monitor.content_quality import ContentQuality, assess_content_quality
from products.tech_blog_monitor.defaults import (
    DEFAULT_CONTENT_EXTRACTOR,
    DEFAULT_CONTENT_MAX_CHARS,
    DEFAULT_CONTENT_TIMEOUT,
    DEFAULT_PLAYWRIGHT_FALLBACK,
    DEFAULT_PLAYWRIGHT_TIMEOUT,
    DEFAULT_PLAYWRIGHT_WORKERS,
)
from products.tech_blog_monitor.extractors import ExtractionResult
from products.tech_blog_monitor.extractors.heuristic_extractor import (
    extract_clean_text as _heuristic_extract_clean_text,
)
from products.tech_blog_monitor.extractors.heuristic_extractor import (
    extract_content as heuristic_extract_content,
)
from products.tech_blog_monitor.extractors.heuristic_extractor import looks_like_js_heavy_page
from products.tech_blog_monitor.extractors.playwright_extractor import (
    extract_content as playwright_extract_content,
)
from products.tech_blog_monitor.extractors.trafilatura_extractor import (
    extract_content as trafilatura_extract_content,
)
from products.tech_blog_monitor.fetcher import Article

_UTC = timezone.utc
_PLAYWRIGHT_SEMAPHORES: dict[int, BoundedSemaphore] = {}
_PLAYWRIGHT_SEMAPHORES_LOCK = Lock()


def extract_clean_text(html_text: str, max_chars: int = DEFAULT_CONTENT_MAX_CHARS) -> tuple[str, str]:
    """兼容 facade：保留旧的启发式正文抽取接口。"""
    return _heuristic_extract_clean_text(html_text, max_chars=max_chars)


def _primary_extractors(
    extractor_name: str,
) -> list[Callable[..., ExtractionResult]]:
    if extractor_name == "heuristic":
        return [heuristic_extract_content, trafilatura_extract_content]
    return [trafilatura_extract_content, heuristic_extract_content]


def _get_playwright_semaphore(workers: int) -> BoundedSemaphore:
    with _PLAYWRIGHT_SEMAPHORES_LOCK:
        semaphore = _PLAYWRIGHT_SEMAPHORES.get(workers)
        if semaphore is None:
            semaphore = BoundedSemaphore(workers)
            _PLAYWRIGHT_SEMAPHORES[workers] = semaphore
        return semaphore


def _apply_extraction_result(
    article: Article,
    result: ExtractionResult,
    *,
    quality: ContentQuality,
) -> Article:
    article.clean_text = result.clean_text
    article.content_source = result.source
    article.content_status = "fetched"
    article.content_error = ""
    logger.debug(
        "正文抽取成功: url={} source={} score={} len={}",
        article.url,
        result.source,
        quality.score,
        quality.text_length,
    )
    return article


def _mark_empty(article: Article, errors: list[str]) -> Article:
    article.clean_text = ""
    article.content_status = "empty"
    article.content_source = ""
    article.content_error = "; ".join(errors) if errors else "未提取到正文"
    return article


def _mark_low_quality(
    article: Article,
    *,
    result: ExtractionResult,
    quality: ContentQuality,
    errors: list[str],
) -> Article:
    article.clean_text = ""
    article.content_status = "low_quality"
    article.content_source = result.source
    details = [
        f"quality={quality.reason}",
        f"score={quality.score}",
    ]
    if errors:
        details.extend(errors)
    article.content_error = "; ".join(details)
    logger.debug(
        "正文质量不足: url={} source={} reason={} score={}",
        article.url,
        result.source,
        quality.reason,
        quality.score,
    )
    return article


def _run_primary_chain(
    html_text: str,
    *,
    url: str,
    max_chars: int,
    extractor_name: str,
) -> tuple[ExtractionResult | None, ContentQuality | None, list[str], bool]:
    errors: list[str] = []
    best_low_quality_result: ExtractionResult | None = None
    best_low_quality: ContentQuality | None = None
    saw_text = False

    for extractor in _primary_extractors(extractor_name):
        result = extractor(html_text, url=url, max_chars=max_chars)
        if not result.clean_text:
            if result.error:
                errors.append(result.error)
            continue
        saw_text = True
        quality = assess_content_quality(result.clean_text)
        if quality.passed:
            return result, quality, errors, saw_text
        if best_low_quality is None or quality.score > best_low_quality.score:
            best_low_quality_result = result
            best_low_quality = quality
        errors.append(f"{result.source}:{quality.reason}")

    return best_low_quality_result, best_low_quality, errors, saw_text


def _should_try_playwright(
    html_text: str,
    *,
    playwright_fallback: bool,
    quality: ContentQuality | None,
    saw_text: bool,
) -> bool:
    if not playwright_fallback:
        return False
    if looks_like_js_heavy_page(html_text):
        return True
    if not saw_text:
        return True
    return quality is not None and not quality.passed


def fetch_article_content(
    article: Article,
    *,
    timeout: int = DEFAULT_CONTENT_TIMEOUT,
    max_chars: int = DEFAULT_CONTENT_MAX_CHARS,
    requester: Optional[requests.Session] = None,
    content_extractor: str = DEFAULT_CONTENT_EXTRACTOR,
    playwright_fallback: bool = DEFAULT_PLAYWRIGHT_FALLBACK,
    playwright_timeout: int = DEFAULT_PLAYWRIGHT_TIMEOUT,
    playwright_workers: int = DEFAULT_PLAYWRIGHT_WORKERS,
) -> Article:
    now_ts = int(datetime.now(_UTC).timestamp())
    get = requester.get if requester is not None else requests.get

    try:
        resp = get(
            article.url,
            timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0"},
            allow_redirects=True,
        )
        article.content_http_status = resp.status_code
        article.content_final_url = str(getattr(resp, "url", article.url) or article.url)
        article.content_fetched_at = now_ts
        if resp.status_code >= 400:
            article.clean_text = ""
            article.content_source = ""
            article.content_status = "http_error"
            article.content_error = f"HTTP {resp.status_code}"
            return article

        html_text = resp.text or ""
        article.raw_html = html_text
        result, quality, errors, saw_text = _run_primary_chain(
            html_text,
            url=article.content_final_url,
            max_chars=max_chars,
            extractor_name=content_extractor,
        )
        if result is not None and quality is not None and quality.passed:
            return _apply_extraction_result(article, result, quality=quality)

        if _should_try_playwright(
            html_text,
            playwright_fallback=playwright_fallback,
            quality=quality,
            saw_text=saw_text,
        ):
            semaphore = _get_playwright_semaphore(playwright_workers)
            with semaphore:
                browser_result = playwright_extract_content(
                    article.content_final_url,
                    timeout_ms=playwright_timeout * 1000,
                    max_chars=max_chars,
                )
            if browser_result.clean_text:
                browser_quality = assess_content_quality(browser_result.clean_text)
                if browser_quality.passed:
                    return _apply_extraction_result(article, browser_result, quality=browser_quality)
                errors.append(f"{browser_result.source}:{browser_quality.reason}")
                if quality is None or browser_quality.score >= quality.score:
                    result = browser_result
                    quality = browser_quality
            elif browser_result.error:
                errors.append(browser_result.error)

        if result is not None and quality is not None:
            return _mark_low_quality(article, result=result, quality=quality, errors=errors)
        return _mark_empty(article, errors)
    except Exception as exc:
        article.clean_text = ""
        article.content_source = ""
        article.content_status = "fetch_error"
        article.content_error = str(exc)
        article.content_fetched_at = now_ts
        article.content_final_url = article.url
        return article


def fetch_contents(
    articles: list[Article],
    *,
    workers: int,
    timeout: int,
    max_chars: int,
    content_extractor: str = DEFAULT_CONTENT_EXTRACTOR,
    playwright_fallback: bool = DEFAULT_PLAYWRIGHT_FALLBACK,
    playwright_timeout: int = DEFAULT_PLAYWRIGHT_TIMEOUT,
    playwright_workers: int = DEFAULT_PLAYWRIGHT_WORKERS,
) -> list[Article]:
    if not articles:
        return articles

    logger.info(
        "并发抓取 {} 篇文章正文（workers={} extractor={} playwright_fallback={}）",
        len(articles),
        workers,
        content_extractor,
        playwright_fallback,
    )
    results: list[Article] = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_article = {
            executor.submit(
                fetch_article_content,
                article,
                timeout=timeout,
                max_chars=max_chars,
                content_extractor=content_extractor,
                playwright_fallback=playwright_fallback,
                playwright_timeout=playwright_timeout,
                playwright_workers=playwright_workers,
            ): article
            for article in articles
        }
        for future in as_completed(future_to_article):
            article = future_to_article[future]
            try:
                results.append(future.result())
            except Exception as exc:  # pragma: no cover - defensive
                article.clean_text = ""
                article.content_source = ""
                article.content_status = "fetch_error"
                article.content_error = str(exc)
                article.content_fetched_at = int(datetime.now(_UTC).timestamp())
                results.append(article)

    order = {id(article): index for index, article in enumerate(articles)}
    results.sort(key=lambda article: order.get(id(article), 0))
    status_counter = Counter(article.content_status for article in results)
    source_counter = Counter(article.content_source for article in results if article.content_source)
    logger.info(
        "正文抓取完成：成功 {} / 空正文 {} / 低质量 {} / 失败 {}",
        status_counter.get("fetched", 0),
        status_counter.get("empty", 0),
        status_counter.get("low_quality", 0),
        status_counter.get("fetch_error", 0) + status_counter.get("http_error", 0),
    )
    if source_counter:
        logger.info("正文抽取来源分布：{}", dict(source_counter))
    return results
