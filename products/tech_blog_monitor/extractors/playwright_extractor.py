# -*- coding: utf-8 -*-
"""Controlled Playwright fallback for JS-heavy pages."""

from __future__ import annotations

from products.tech_blog_monitor.extractors import ExtractionResult
from products.tech_blog_monitor.extractors.heuristic_extractor import (
    extract_content as heuristic_extract_content,
)
from products.tech_blog_monitor.extractors.trafilatura_extractor import (
    extract_content as trafilatura_extract_content,
)

try:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright
except Exception:  # pragma: no cover - optional import failure
    PlaywrightTimeoutError = TimeoutError
    sync_playwright = None


def extract_content(
    url: str,
    *,
    timeout_ms: int,
    max_chars: int,
) -> ExtractionResult:
    if sync_playwright is None:
        return ExtractionResult(
            clean_text="",
            source="playwright",
            error="playwright_unavailable",
            metadata={"extractor": "playwright"},
        )

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(user_agent="Mozilla/5.0")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                try:
                    page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 3000))
                except PlaywrightTimeoutError:
                    pass
                html_text = page.content()
            finally:
                browser.close()
    except Exception as exc:  # pragma: no cover - browser path is mock-tested
        return ExtractionResult(
            clean_text="",
            source="playwright",
            error=f"playwright_error: {exc}",
            metadata={"extractor": "playwright"},
        )

    result = trafilatura_extract_content(html_text, url=url, max_chars=max_chars)
    if result.clean_text:
        return ExtractionResult(
            clean_text=result.clean_text,
            source=f"playwright_{result.source}",
            error="",
            metadata={"extractor": "playwright", "rendered": True},
        )

    fallback = heuristic_extract_content(html_text, max_chars=max_chars)
    if fallback.clean_text:
        return ExtractionResult(
            clean_text=fallback.clean_text,
            source=f"playwright_{fallback.source}",
            error="",
            metadata={"extractor": "playwright", "rendered": True},
        )

    return ExtractionResult(
        clean_text="",
        source="playwright",
        error=result.error or fallback.error or "playwright_empty",
        metadata={"extractor": "playwright", "rendered": True},
    )
