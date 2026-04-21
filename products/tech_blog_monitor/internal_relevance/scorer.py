"""Rule-based internal relevance scoring."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy

from products.tech_blog_monitor.fetcher import Article
from products.tech_blog_monitor.internal_relevance.models import (
    RelevanceReport,
    StackProfile,
    StackSignal,
)

_DEPENDENCY_FIELD_WEIGHTS = {
    "title": 2.5,
    "tags": 2.0,
    "topic": 1.8,
    "summary": 1.2,
    "clean_text": 0.8,
}
_TOPIC_FIELD_WEIGHTS = {
    "title": 2.0,
    "tags": 1.8,
    "topic": 1.6,
    "summary": 1.0,
    "clean_text": 0.6,
}
_RELEVANCE_LEVEL_THRESHOLDS = (
    ("high", 6.0),
    ("medium", 3.0),
    ("low", 1.0),
)


def _normalize_text(value: str) -> str:
    return " ".join(value.lower().split())


def _article_field_texts(article: Article) -> dict[str, str]:
    summary_text = " ".join(
        value for value in [
            article.rss_summary,
            article.ai_summary,
            article.one_line_summary,
            article.why_it_matters,
        ] if value
    )
    return {
        "title": _normalize_text(article.title),
        "tags": _normalize_text(" ".join(article.tags)),
        "topic": _normalize_text(article.topic),
        "summary": _normalize_text(summary_text),
        "clean_text": _normalize_text(article.clean_text),
    }


def _collect_matches(signal_terms: list[str], field_texts: dict[str, str], field_weights: dict[str, float]) -> tuple[float, list[str], list[str]]:
    score = 0.0
    matched_fields: list[str] = []
    matched_terms: set[str] = set()
    for field_name, text in field_texts.items():
        if not text:
            continue
        field_terms = [term for term in signal_terms if term and term in text]
        if not field_terms:
            continue
        score += field_weights[field_name]
        matched_fields.append(field_name)
        matched_terms.update(field_terms)
    return score, matched_fields, sorted(matched_terms)


def _merge_signals(profile: StackProfile, scanned_signals: list[StackSignal]) -> list[StackSignal]:
    merged: dict[tuple[str, str], StackSignal] = {}
    for signal in [*profile.signals, *scanned_signals]:
        key = (signal.kind, signal.name)
        existing = merged.get(key)
        if existing is None:
            merged[key] = deepcopy(signal)
            continue
        existing.aliases = sorted(set(existing.aliases).union(signal.aliases))
        existing.keywords = sorted(set(existing.keywords).union(signal.keywords))
        existing.weight = max(existing.weight, signal.weight)
        existing.source = existing.source or signal.source
        if signal.source_detail and signal.source_detail not in existing.source_detail:
            existing.source_detail = ", ".join(
                item for item in [existing.source_detail, signal.source_detail] if item
            )
    return list(merged.values())


def _compute_source_priority(article: Article, source_priorities: dict[str, float]) -> float:
    return float(source_priorities.get((article.source_type or "rss").strip().lower(), 0.0))


def _resolve_level(score: float) -> str:
    for level, threshold in _RELEVANCE_LEVEL_THRESHOLDS:
        if score >= threshold:
            return level
    return "none"


def evaluate_internal_relevance(
    articles: list[Article],
    *,
    profile: StackProfile,
    scanned_signals: list[StackSignal],
    scanned_repo_roots: list[str],
    scanned_manifest_count: int,
    warnings: list[str],
) -> tuple[list[Article], RelevanceReport]:
    merged_signals = _merge_signals(profile, scanned_signals)
    dependency_signals = [signal for signal in merged_signals if signal.kind == "dependency"]
    topic_signals = [signal for signal in merged_signals if signal.kind == "topic"]

    if not merged_signals:
        return articles, RelevanceReport(
            status="skipped",
            summary="未配置技术栈画像或 repo manifest，已跳过 internal relevance。",
            signal_count=0,
            dependency_signal_count=0,
            topic_signal_count=0,
            scanned_repo_roots=[root for root in scanned_repo_roots if root],
            scanned_manifest_count=scanned_manifest_count,
            article_count=len(articles),
            matched_article_count=0,
            level_counts={},
            top_matches=[],
            warnings=warnings,
        )

    source_priorities = profile.source_priorities or {}
    for article in articles:
        field_texts = _article_field_texts(article)
        dependency_score = 0.0
        topic_score = 0.0
        reasons: list[str] = []
        matched_signals: list[dict[str, object]] = []

        for signal in dependency_signals:
            terms = sorted(set(alias for alias in signal.aliases if alias))
            if signal.name not in terms:
                terms.append(signal.name)
            raw_score, matched_fields, matched_terms = _collect_matches(
                terms,
                field_texts,
                _DEPENDENCY_FIELD_WEIGHTS,
            )
            if raw_score <= 0:
                continue
            score = raw_score * signal.weight
            dependency_score += score
            reasons.append(
                f"dependency:{signal.name} 命中 {', '.join(matched_fields)}"
            )
            matched_signals.append(
                {
                    "signal_id": signal.signal_id,
                    "signal_name": signal.name,
                    "signal_kind": signal.kind,
                    "matched_terms": matched_terms,
                    "matched_fields": matched_fields,
                    "score": round(score, 3),
                    "source": signal.source,
                }
            )

        for signal in topic_signals:
            terms = sorted(set(keyword for keyword in signal.keywords if keyword))
            raw_score, matched_fields, matched_terms = _collect_matches(
                terms,
                field_texts,
                _TOPIC_FIELD_WEIGHTS,
            )
            if raw_score <= 0:
                continue
            score = raw_score * signal.weight
            topic_score += score
            reasons.append(
                f"topic:{signal.name} 命中 {', '.join(matched_fields)}"
            )
            matched_signals.append(
                {
                    "signal_id": signal.signal_id,
                    "signal_name": signal.name,
                    "signal_kind": signal.kind,
                    "matched_terms": matched_terms,
                    "matched_fields": matched_fields,
                    "score": round(score, 3),
                    "source": signal.source,
                }
            )

        source_priority_score = _compute_source_priority(article, source_priorities)
        if dependency_score <= 0 and topic_score <= 0:
            source_priority_score = 0.0
        elif source_priority_score > 0:
            reasons.append(
                f"source_priority:{article.source_type} 加权 {source_priority_score:.2f}"
            )

        relevance_score = dependency_score + topic_score + source_priority_score
        article.dependency_match_score = round(dependency_score, 3)
        article.topic_match_score = round(topic_score, 3)
        article.source_priority_score = round(source_priority_score, 3)
        article.relevance_score = round(relevance_score, 3)
        article.relevance_level = _resolve_level(relevance_score)
        article.relevance_reasons = reasons
        article.matched_signals = matched_signals

    matched_articles = [article for article in articles if article.relevance_score > 0]
    level_counts = dict(Counter(article.relevance_level for article in matched_articles))
    top_matches = [
        {
            "title": article.title,
            "url": article.url,
            "source_name": article.source_name,
            "source_type": article.source_type,
            "relevance_score": article.relevance_score,
            "relevance_level": article.relevance_level,
            "matched_signal_names": [item["signal_name"] for item in article.matched_signals],
        }
        for article in sorted(
            matched_articles,
            key=lambda item: (item.relevance_score, item.published_ts or 0),
            reverse=True,
        )[:5]
    ]

    return articles, RelevanceReport(
        status="ok",
        summary=(
            f"完成 internal relevance：{len(matched_articles)}/{len(articles)} 篇文章命中内部技术栈信号，"
            f"共 {len(merged_signals)} 个信号。"
        ),
        signal_count=len(merged_signals),
        dependency_signal_count=len(dependency_signals),
        topic_signal_count=len(topic_signals),
        scanned_repo_roots=[root for root in scanned_repo_roots if root],
        scanned_manifest_count=scanned_manifest_count,
        article_count=len(articles),
        matched_article_count=len(matched_articles),
        level_counts=level_counts,
        top_matches=top_matches,
        warnings=warnings,
    )
