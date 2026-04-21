# -*- coding: utf-8 -*-
"""Heuristic HTML content extraction fallback."""

from __future__ import annotations

import html
import json
import re
from typing import Optional

from products.tech_blog_monitor.extractors import ExtractionResult

_BLOCK_TAGS_RE = re.compile(
    r"(?is)<(script|style|noscript|svg|iframe|canvas|template|header|nav|footer|aside|form)[^>]*>.*?</\1>"
)
_COMMENT_RE = re.compile(r"(?is)<!--.*?-->")
_TAG_RE = re.compile(r"(?is)<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")
_ARTICLE_RE = re.compile(r"(?is)<article\b[^>]*>(.*?)</article>")
_MAIN_RE = re.compile(r"(?is)<main\b[^>]*>(.*?)</main>")
_BODY_RE = re.compile(r"(?is)<body\b[^>]*>(.*?)</body>")
_GENERIC_CONTENT_RE = re.compile(
    r'(?is)<(?:div|section)\b[^>]*(?:id|class)=["\'][^"\']*(?:content|article|post|entry|main)[^"\']*["\'][^>]*>(.*?)</(?:div|section)>'
)
_JSON_LD_RE = re.compile(
    r'(?is)<script\b[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>'
)
_JS_HEAVY_MARKERS = (
    "__next",
    "__nuxt",
    "data-reactroot",
    "data-react-helmet",
    "window.__initial_state__",
    "window.__nuxt__",
    "hydration",
    'id="root"',
    "webpack",
)


def _html_to_text(fragment: str, max_chars: int) -> str:
    stripped = _BLOCK_TAGS_RE.sub(" ", fragment)
    stripped = _COMMENT_RE.sub(" ", stripped)
    stripped = re.sub(r"(?i)<br\s*/?>", "\n", stripped)
    stripped = re.sub(r"(?i)</(p|div|section|article|main|li|h[1-6]|tr)>", "\n", stripped)
    stripped = _TAG_RE.sub(" ", stripped)
    stripped = html.unescape(stripped)
    lines = [_WHITESPACE_RE.sub(" ", line).strip() for line in stripped.splitlines()]
    text = "\n".join(line for line in lines if line)
    return text[:max_chars].strip()


def _extract_article_body_from_json_ld(html_text: str) -> str:
    def _find_article_body(value: object) -> Optional[str]:
        if isinstance(value, dict):
            article_body = value.get("articleBody")
            if isinstance(article_body, str) and article_body.strip():
                return article_body.strip()
            for nested in value.values():
                result = _find_article_body(nested)
                if result:
                    return result
        elif isinstance(value, list):
            for item in value:
                result = _find_article_body(item)
                if result:
                    return result
        return None

    for match in _JSON_LD_RE.finditer(html_text):
        raw = html.unescape(match.group(1)).strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        result = _find_article_body(data)
        if result:
            return _WHITESPACE_RE.sub(" ", result).strip()
    return ""


def extract_clean_text(html_text: str, max_chars: int = 20000) -> tuple[str, str]:
    for regex, source in (
        (_ARTICLE_RE, "html_article"),
        (_MAIN_RE, "html_main"),
        (_GENERIC_CONTENT_RE, "html_content_block"),
        (_BODY_RE, "html_body"),
    ):
        match = regex.search(html_text)
        if not match:
            continue
        text = _html_to_text(match.group(1), max_chars=max_chars)
        if text:
            return text, source

    json_ld_text = _extract_article_body_from_json_ld(html_text)
    if json_ld_text:
        return json_ld_text[:max_chars], "json_ld"

    return "", ""


def extract_content(
    html_text: str,
    *,
    max_chars: int = 20000,
    url: str = "",
) -> ExtractionResult:
    clean_text, source = extract_clean_text(html_text, max_chars=max_chars)
    return ExtractionResult(
        clean_text=clean_text,
        source=source,
        error="" if clean_text else "heuristic_empty",
        metadata={"extractor": "heuristic"},
    )


def looks_like_js_heavy_page(html_text: str) -> bool:
    lowered = (html_text or "").lower()
    if any(marker in lowered for marker in _JS_HEAVY_MARKERS):
        return True
    return lowered.count("<script") >= 8 and len(_html_to_text(lowered, max_chars=300)) < 80
