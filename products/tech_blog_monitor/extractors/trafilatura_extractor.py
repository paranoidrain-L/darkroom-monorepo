# -*- coding: utf-8 -*-
"""Trafilatura-based primary content extractor."""

from __future__ import annotations

try:
    import trafilatura
except Exception:  # pragma: no cover - optional import failure
    trafilatura = None

from products.tech_blog_monitor.extractors import ExtractionResult


def extract_content(
    html_text: str,
    *,
    url: str = "",
    max_chars: int = 20000,
) -> ExtractionResult:
    if trafilatura is None:
        return ExtractionResult(
            clean_text="",
            source="trafilatura",
            error="trafilatura_unavailable",
            metadata={"extractor": "trafilatura"},
        )

    try:
        extracted = trafilatura.extract(
            html_text,
            url=url or None,
            output_format="txt",
            include_comments=False,
            include_tables=True,
            favor_precision=True,
            deduplicate=True,
        )
    except Exception as exc:  # pragma: no cover - defensive
        return ExtractionResult(
            clean_text="",
            source="trafilatura",
            error=f"trafilatura_error: {exc}",
            metadata={"extractor": "trafilatura"},
        )

    clean_text = (extracted or "").strip()
    return ExtractionResult(
        clean_text=clean_text[:max_chars],
        source="trafilatura",
        error="" if clean_text else "trafilatura_empty",
        metadata={"extractor": "trafilatura"},
    )
