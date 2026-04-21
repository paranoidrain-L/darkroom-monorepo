# -*- coding: utf-8 -*-
"""Tech Blog Monitor - Phase 5 正文 chunk 切分。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List, Sequence

from products.tech_blog_monitor.fetcher import Article

_MAX_CHUNK_CHARS = 600
_CHUNK_OVERLAP_CHARS = 120


@dataclass
class ChunkPayload:
    chunk_index: int
    source_kind: str
    text: str


def _normalize_text(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"[ \t]+", " ", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def _join_nonempty(parts: Iterable[str]) -> str:
    return "\n".join(part.strip() for part in parts if isinstance(part, str) and part.strip())


def _slice_with_overlap(text: str, chunk_size: int, overlap: int) -> List[str]:
    if len(text) <= chunk_size:
        return [text]

    chunks: List[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + chunk_size)
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks


def _split_text(text: str, chunk_size: int, overlap: int) -> List[str]:
    paragraphs = [segment.strip() for segment in text.split("\n\n") if segment.strip()]
    if not paragraphs:
        return []

    chunks: List[str] = []
    current = ""
    for paragraph in paragraphs:
        candidate = paragraph if not current else f"{current}\n\n{paragraph}"
        if len(candidate) <= chunk_size:
            current = candidate
            continue
        if current:
            chunks.append(current)
        if len(paragraph) <= chunk_size:
            current = paragraph
        else:
            long_parts = _slice_with_overlap(paragraph, chunk_size, overlap)
            chunks.extend(long_parts[:-1])
            current = long_parts[-1]

    if current:
        chunks.append(current)

    # Add lightweight overlap between paragraph-level chunks to improve recall.
    overlapped: List[str] = []
    for index, piece in enumerate(chunks):
        if index == 0:
            overlapped.append(piece)
            continue
        prefix = chunks[index - 1][-overlap:].strip()
        if prefix:
            overlapped.append(f"{prefix}\n{piece}".strip())
        else:
            overlapped.append(piece)
    return overlapped


def build_chunk_source_text(
    *,
    title: str,
    clean_text: str = "",
    rss_summary: str = "",
    one_line_summary: str = "",
    why_it_matters: str = "",
    key_points: Sequence[str] | None = None,
) -> tuple[str, str]:
    normalized_clean_text = _normalize_text(clean_text)
    if normalized_clean_text:
        return normalized_clean_text, "clean_text"

    fallback = _join_nonempty(
        [
            title,
            one_line_summary,
            rss_summary,
            why_it_matters,
            _join_nonempty(key_points or []),
        ]
    )
    return _normalize_text(fallback), "summary_fallback"


def build_chunks_from_fields(
    *,
    title: str,
    clean_text: str = "",
    rss_summary: str = "",
    one_line_summary: str = "",
    why_it_matters: str = "",
    key_points: Sequence[str] | None = None,
    chunk_size: int = _MAX_CHUNK_CHARS,
    overlap: int = _CHUNK_OVERLAP_CHARS,
) -> List[ChunkPayload]:
    source_text, source_kind = build_chunk_source_text(
        title=title,
        clean_text=clean_text,
        rss_summary=rss_summary,
        one_line_summary=one_line_summary,
        why_it_matters=why_it_matters,
        key_points=key_points,
    )
    if not source_text:
        return []

    return [
        ChunkPayload(chunk_index=index, source_kind=source_kind, text=text)
        for index, text in enumerate(_split_text(source_text, chunk_size=chunk_size, overlap=overlap))
        if text
    ]


def build_chunks_for_article(
    article: Article,
    *,
    chunk_size: int = _MAX_CHUNK_CHARS,
    overlap: int = _CHUNK_OVERLAP_CHARS,
) -> List[ChunkPayload]:
    return build_chunks_from_fields(
        title=article.title,
        clean_text=article.clean_text,
        rss_summary=article.rss_summary,
        one_line_summary=article.one_line_summary,
        why_it_matters=article.why_it_matters,
        key_points=article.key_points,
        chunk_size=chunk_size,
        overlap=overlap,
    )
