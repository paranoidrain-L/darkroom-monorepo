# -*- coding: utf-8 -*-
"""Content quality assessment for extracted article text."""

from __future__ import annotations

from dataclasses import dataclass

_NAVIGATION_PATTERNS = (
    "home",
    "about",
    "contact",
    "login",
    "log in",
    "sign in",
    "subscribe",
    "privacy",
    "terms",
    "cookie",
    "menu",
    "search",
)


@dataclass(frozen=True)
class ContentQuality:
    passed: bool
    score: int
    reason: str
    text_length: int
    paragraph_count: int
    repeated_line_ratio: float
    navigation_noise_ratio: float


def assess_content_quality(text: str) -> ContentQuality:
    stripped = "\n".join(line.strip() for line in (text or "").splitlines() if line.strip())
    if not stripped:
        return ContentQuality(
            passed=False,
            score=0,
            reason="empty_text",
            text_length=0,
            paragraph_count=0,
            repeated_line_ratio=0.0,
            navigation_noise_ratio=0.0,
        )

    lines = [line for line in stripped.splitlines() if line]
    unique_lines = set(lines)
    repeated_line_ratio = 0.0 if not lines else 1.0 - len(unique_lines) / len(lines)
    paragraph_count = len(lines)
    lower_text = stripped.lower()
    navigation_hits = sum(lower_text.count(pattern) for pattern in _NAVIGATION_PATTERNS)
    navigation_noise_ratio = navigation_hits / max(len(lower_text.split()), 1)
    text_length = len(stripped)

    score = 100
    reason = "ok"

    if text_length < 40:
        score -= 35
        reason = "too_short"
    elif text_length < 80:
        score -= 10
    if paragraph_count < 2:
        score -= 10
        reason = "too_few_paragraphs" if reason == "ok" else reason
    if repeated_line_ratio > 0.35:
        score -= 20
        reason = "repetitive_content" if reason == "ok" else reason
    if navigation_noise_ratio > 0.12:
        score -= 35
        reason = "navigation_noise" if reason == "ok" else reason

    passed = (
        score >= 50
        and text_length >= 40
        and repeated_line_ratio <= 0.5
        and navigation_noise_ratio <= 0.2
    )
    return ContentQuality(
        passed=passed,
        score=max(score, 0),
        reason=reason if not passed else "ok",
        text_length=text_length,
        paragraph_count=paragraph_count,
        repeated_line_ratio=repeated_line_ratio,
        navigation_noise_ratio=navigation_noise_ratio,
    )
