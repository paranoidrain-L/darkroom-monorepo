# -*- coding: utf-8 -*-
"""Tech Blog Monitor - Phase 6 分析型产品能力。"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from time import perf_counter
from typing import Dict, List, Sequence

from products.tech_blog_monitor.observability.metrics import get_default_metrics_registry
from products.tech_blog_monitor.repository_provider import open_repository_bundle

_DAY_SECONDS = 86400


@dataclass
class InsightQuery:
    days: int = 14
    top_k: int = 5
    max_articles: int = 1000
    anchor_ts: int | None = None


@dataclass
class TopicCluster:
    topic: str
    article_count: int
    source_count: int
    representative_titles: List[str]
    trend_label: str
    delta: int


@dataclass
class SourceComparison:
    source_name: str
    article_count: int
    dominant_topics: List[str]
    unique_topic_count: int


@dataclass
class TimelinePoint:
    date: str
    article_count: int
    top_topic: str


@dataclass
class HotSignal:
    topic: str
    score: float
    reason: str


@dataclass
class InsightReport:
    status: str
    summary: str
    topic_clusters: List[TopicCluster]
    source_comparisons: List[SourceComparison]
    timeline: List[TimelinePoint]
    hot_signals: List[HotSignal]


def _article_ts(article: Dict[str, object]) -> int:
    published_ts = article.get("published_ts")
    if isinstance(published_ts, int):
        return published_ts
    last_seen_at = article.get("last_seen_at")
    if isinstance(last_seen_at, int):
        return last_seen_at
    return 0


def _article_topic(article: Dict[str, object]) -> str:
    topic = article.get("topic")
    if isinstance(topic, str) and topic.strip():
        return topic.strip()
    category = article.get("category")
    if isinstance(category, str) and category.strip():
        return category.strip()
    return "未分类"


def _window_articles(
    articles: Sequence[Dict[str, object]],
    *,
    start_ts: int,
    end_ts: int,
) -> List[Dict[str, object]]:
    return [
        article for article in articles
        if start_ts <= _article_ts(article) < end_ts
    ]


def _trend_label(recent_count: int, previous_count: int) -> tuple[str, int]:
    delta = recent_count - previous_count
    if delta >= 2:
        return "rising", delta
    if delta <= -2:
        return "falling", delta
    return "stable", delta


def _build_topic_clusters(
    recent_articles: Sequence[Dict[str, object]],
    previous_articles: Sequence[Dict[str, object]],
    *,
    top_k: int,
) -> List[TopicCluster]:
    recent_groups: dict[str, list[Dict[str, object]]] = defaultdict(list)
    previous_counts: Counter[str] = Counter()
    for article in recent_articles:
        recent_groups[_article_topic(article)].append(article)
    for article in previous_articles:
        previous_counts[_article_topic(article)] += 1

    clusters: List[TopicCluster] = []
    for topic, items in recent_groups.items():
        trend_label, delta = _trend_label(len(items), previous_counts.get(topic, 0))
        representative_titles = [
            str(item.get("title", ""))
            for item in sorted(items, key=_article_ts, reverse=True)[:3]
            if str(item.get("title", ""))
        ]
        source_names = {
            str(item.get("source_name", ""))
            for item in items
            if str(item.get("source_name", ""))
        }
        clusters.append(
            TopicCluster(
                topic=topic,
                article_count=len(items),
                source_count=len(source_names),
                representative_titles=representative_titles,
                trend_label=trend_label,
                delta=delta,
            )
        )

    clusters.sort(
        key=lambda item: (
            item.article_count,
            item.delta,
            item.source_count,
            item.topic,
        ),
        reverse=True,
    )
    return clusters[:top_k]


def _build_source_comparisons(
    recent_articles: Sequence[Dict[str, object]],
    *,
    top_k: int,
) -> List[SourceComparison]:
    groups: dict[str, list[Dict[str, object]]] = defaultdict(list)
    for article in recent_articles:
        source_name = str(article.get("source_name", "")).strip() or "unknown"
        groups[source_name].append(article)

    comparisons: List[SourceComparison] = []
    for source_name, items in groups.items():
        topic_counter = Counter(_article_topic(item) for item in items)
        dominant_topics = [
            topic
            for topic, _ in topic_counter.most_common(3)
            if topic
        ]
        comparisons.append(
            SourceComparison(
                source_name=source_name,
                article_count=len(items),
                dominant_topics=dominant_topics,
                unique_topic_count=len(topic_counter),
            )
        )

    comparisons.sort(
        key=lambda item: (
            item.article_count,
            item.unique_topic_count,
            item.source_name,
        ),
        reverse=True,
    )
    return comparisons[:top_k]


def _build_timeline(
    recent_articles: Sequence[Dict[str, object]],
    *,
    start_ts: int,
    days: int,
) -> List[TimelinePoint]:
    per_day: dict[str, list[Dict[str, object]]] = defaultdict(list)
    for article in recent_articles:
        dt = datetime.fromtimestamp(_article_ts(article), tz=timezone.utc)
        per_day[dt.strftime("%Y-%m-%d")].append(article)

    points: List[TimelinePoint] = []
    for offset in range(days):
        day_ts = start_ts + offset * _DAY_SECONDS
        day = datetime.fromtimestamp(day_ts, tz=timezone.utc).strftime("%Y-%m-%d")
        articles = per_day.get(day, [])
        topic_counter = Counter(_article_topic(article) for article in articles)
        top_topic = topic_counter.most_common(1)[0][0] if topic_counter else ""
        points.append(
            TimelinePoint(
                date=day,
                article_count=len(articles),
                top_topic=top_topic,
            )
        )
    return points


def _build_hot_signals(
    clusters: Sequence[TopicCluster],
    *,
    top_k: int,
) -> List[HotSignal]:
    signals: List[HotSignal] = []
    for cluster in clusters:
        cross_source_bonus = 0.5 * max(cluster.source_count - 1, 0)
        momentum = max(cluster.delta, 0)
        score = cluster.article_count * 1.5 + momentum + cross_source_bonus
        if cluster.article_count < 2 and momentum <= 0:
            continue

        if cluster.trend_label == "rising":
            reason = f"最近窗口比上一窗口多 {cluster.delta} 篇"
        elif cluster.source_count >= 2:
            reason = f"最近窗口覆盖 {cluster.source_count} 个来源"
        else:
            reason = f"最近窗口有 {cluster.article_count} 篇相关文章"
        signals.append(HotSignal(topic=cluster.topic, score=score, reason=reason))

    signals.sort(key=lambda item: (item.score, item.topic), reverse=True)
    return signals[:top_k]


def _fact_summary(
    *,
    total_articles: int,
    source_count: int,
    topic_clusters: Sequence[TopicCluster],
) -> str:
    if not topic_clusters:
        return f"样本不足，当前仅有 {total_articles} 篇文章，暂时只能提供事实汇总。"
    top_topics = "、".join(cluster.topic for cluster in topic_clusters[:3])
    return (
        f"样本不足或趋势不显著，当前基于 {total_articles} 篇文章、{source_count} 个来源输出事实汇总；"
        f"主要主题为 {top_topics}。"
    )


def _insight_summary(
    *,
    recent_articles: Sequence[Dict[str, object]],
    source_comparisons: Sequence[SourceComparison],
    topic_clusters: Sequence[TopicCluster],
    hot_signals: Sequence[HotSignal],
    degraded: bool,
) -> str:
    source_count = len({str(article.get("source_name", "")) for article in recent_articles})
    if degraded:
        return _fact_summary(
            total_articles=len(recent_articles),
            source_count=source_count,
            topic_clusters=topic_clusters,
        )

    rising = [cluster.topic for cluster in topic_clusters if cluster.trend_label == "rising"]
    falling = [cluster.topic for cluster in topic_clusters if cluster.trend_label == "falling"]
    source_focus = ""
    if source_comparisons:
        primary = source_comparisons[0]
        if primary.dominant_topics:
            source_focus = (
                f"{primary.source_name} 近期更集中在 {primary.dominant_topics[0]}。"
            )
    signal_focus = ""
    if hot_signals:
        signal_focus = f"当前最强热点信号是 {hot_signals[0].topic}。"

    summary_parts = [
        f"最近窗口共分析 {len(recent_articles)} 篇文章，覆盖 {source_count} 个来源。",
    ]
    if rising:
        summary_parts.append(f"上升主题包括 {'、'.join(rising[:3])}。")
    if falling:
        summary_parts.append(f"下降主题包括 {'、'.join(falling[:3])}。")
    if source_focus:
        summary_parts.append(source_focus)
    if signal_focus:
        summary_parts.append(signal_focus)
    return "".join(summary_parts)


def _analyze_articles(
    articles: Sequence[Dict[str, object]],
    query: InsightQuery,
) -> InsightReport:
    articles = list(articles)
    articles = [article for article in articles if _article_ts(article) > 0]
    if not articles:
        return InsightReport(
            status="insufficient_data",
            summary="资产库中没有可用于分析的时间序列文章。",
            topic_clusters=[],
            source_comparisons=[],
            timeline=[],
            hot_signals=[],
        )

    anchor_ts = query.anchor_ts or max(_article_ts(article) for article in articles) + 1
    recent_start_ts = anchor_ts - query.days * _DAY_SECONDS
    previous_start_ts = anchor_ts - query.days * _DAY_SECONDS * 2
    scoped_articles = _window_articles(
        articles,
        start_ts=previous_start_ts,
        end_ts=anchor_ts,
    )
    recent_articles = _window_articles(
        scoped_articles,
        start_ts=recent_start_ts,
        end_ts=anchor_ts,
    )
    previous_articles = _window_articles(
        scoped_articles,
        start_ts=previous_start_ts,
        end_ts=recent_start_ts,
    )

    topic_clusters = _build_topic_clusters(
        recent_articles,
        previous_articles,
        top_k=query.top_k,
    )
    source_comparisons = _build_source_comparisons(recent_articles, top_k=query.top_k)
    timeline = _build_timeline(
        recent_articles,
        start_ts=recent_start_ts,
        days=query.days,
    )
    hot_signals = _build_hot_signals(topic_clusters, top_k=query.top_k)

    degraded = False
    status = "ok"
    if len(recent_articles) < 3:
        degraded = True
        status = "insufficient_data"
    elif not any(cluster.trend_label != "stable" for cluster in topic_clusters):
        degraded = True
        status = "low_signal"
    elif len(source_comparisons) < 2:
        degraded = True
        status = "unbalanced_sources"

    summary = _insight_summary(
        recent_articles=recent_articles,
        source_comparisons=source_comparisons,
        topic_clusters=topic_clusters,
        hot_signals=hot_signals,
        degraded=degraded,
    )
    return InsightReport(
        status=status,
        summary=summary,
        topic_clusters=topic_clusters,
        source_comparisons=source_comparisons,
        timeline=timeline,
        hot_signals=hot_signals,
    )


def analyze_insights(
    db_path: str,
    query: InsightQuery | None = None,
    *,
    database_url: str = "",
) -> InsightReport:
    started = perf_counter()
    status = "success"
    query = query or InsightQuery()
    try:
        with open_repository_bundle(asset_db_path=db_path, database_url=database_url) as bundle:
            articles = bundle.article_repository.list_articles(limit=query.max_articles)
        report = _analyze_articles(articles, query)
        status = report.status
        return report
    except Exception:
        status = "failed"
        raise
    finally:
        get_default_metrics_registry().observe_insights_latency(
            (perf_counter() - started) * 1000,
            dimensions={
                "status": status,
                "has_database_url": bool(database_url),
            },
        )


def format_insight_report(report: InsightReport) -> str:
    lines = ["# Tech Blog Insights", "", f"状态: {report.status}", "", report.summary, ""]

    lines.extend(["## 主题簇", ""])
    if report.topic_clusters:
        for cluster in report.topic_clusters:
            titles = " | ".join(cluster.representative_titles)
            lines.append(
                f"- {cluster.topic}: {cluster.article_count} 篇, {cluster.source_count} 个来源, "
                f"trend={cluster.trend_label}, delta={cluster.delta}"
            )
            if titles:
                lines.append(f"  代表文章: {titles}")
    else:
        lines.append("- 无可用主题簇")
    lines.append("")

    lines.extend(["## 多来源对比", ""])
    if report.source_comparisons:
        for item in report.source_comparisons:
            topics = "、".join(item.dominant_topics) if item.dominant_topics else "无"
            lines.append(
                f"- {item.source_name}: {item.article_count} 篇, 主题集中在 {topics}, "
                f"unique_topics={item.unique_topic_count}"
            )
    else:
        lines.append("- 无可用来源对比")
    lines.append("")

    lines.extend(["## 时间线", ""])
    if report.timeline:
        for point in report.timeline:
            top_topic = point.top_topic or "无"
            lines.append(f"- {point.date}: {point.article_count} 篇, top_topic={top_topic}")
    else:
        lines.append("- 无时间线数据")
    lines.append("")

    lines.extend(["## 热点信号", ""])
    if report.hot_signals:
        for signal in report.hot_signals:
            lines.append(f"- {signal.topic}: score={signal.score:.2f}, {signal.reason}")
    else:
        lines.append("- 当前没有明显热点信号")

    return "\n".join(lines)
