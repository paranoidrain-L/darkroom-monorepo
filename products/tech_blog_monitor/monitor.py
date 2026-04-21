# -*- coding: utf-8 -*-
"""
Tech Blog Monitor — 核心执行逻辑
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Dict, List, Optional

from loguru import logger

from products.tech_blog_monitor.analyzer import analyze
from products.tech_blog_monitor.archive_store import ArchiveStore
from products.tech_blog_monitor.config import TechBlogMonitorConfig
from products.tech_blog_monitor.content_fetcher import fetch_contents
from products.tech_blog_monitor.db.schema_manager import mirror_sqlite_asset_db
from products.tech_blog_monitor.delivery import DeliveryRequest, maybe_dispatch_deliveries
from products.tech_blog_monitor.fetcher import Article, FeedHealth, fetch_all
from products.tech_blog_monitor.insights import InsightQuery, analyze_insights
from products.tech_blog_monitor.internal_relevance import (
    evaluate_internal_relevance,
    load_stack_profile,
    scan_repo_roots,
)
from products.tech_blog_monitor.internal_relevance.models import RelevanceReport
from products.tech_blog_monitor.observability import (
    CompositeObserver,
    JsonlObserver,
    MetricsObserver,
    RunContext,
    TracingObserver,
    build_tracing_bridge,
    configure_default_metrics_registry,
)
from products.tech_blog_monitor.reporter import build_report
from products.tech_blog_monitor.state import ArticleStateStore

_UTC = timezone.utc


def _serialize_article(article: Article) -> Dict[str, Any]:
    return {
        "title": article.title,
        "url": article.url,
        "source_name": article.source_name,
        "source_type": article.source_type,
        "category": article.category,
        "source_id": article.source_id,
        "published_ts": article.published_ts,
        "fetched_at": article.fetched_at,
        "rss_summary": article.rss_summary,
        "ai_summary": article.ai_summary,
        "content_status": article.content_status,
        "content_source": article.content_source,
        "clean_text": article.clean_text,
        "content_error": article.content_error,
        "content_http_status": article.content_http_status,
        "content_fetched_at": article.content_fetched_at,
        "content_final_url": article.content_final_url,
        "one_line_summary": article.one_line_summary,
        "key_points": article.key_points,
        "why_it_matters": article.why_it_matters,
        "recommended_for": article.recommended_for,
        "tags": article.tags,
        "topic": article.topic,
        "enrichment_status": article.enrichment_status,
        "enrichment_error": article.enrichment_error,
        "relevance_score": article.relevance_score,
        "relevance_level": article.relevance_level,
        "relevance_reasons": article.relevance_reasons,
        "matched_signals": article.matched_signals,
        "dependency_match_score": article.dependency_match_score,
        "topic_match_score": article.topic_match_score,
        "source_priority_score": article.source_priority_score,
    }


def _serialize_health(health: FeedHealth) -> Dict[str, Any]:
    return {
        "name": health.name,
        "url": health.url,
        "source_type": health.source_type,
        "success": health.success,
        "article_count": health.article_count,
        "error": health.error,
        "retries": health.retries,
    }


def _build_json_payload(
    config: TechBlogMonitorConfig,
    all_articles: List[Article],
    report_articles: List[Article],
    health_list: List[FeedHealth],
    new_urls: set[str],
    generated_at: datetime,
    relevance_report: RelevanceReport,
) -> Dict[str, Any]:
    new_articles = [article for article in all_articles if article.url in new_urls]
    data: Dict[str, Any] = {
        "generated_at": int(generated_at.timestamp()),
        "generated_at_iso": generated_at.isoformat(),
        "view": config.view,
        "incremental_mode": config.incremental_mode,
        "asset_db_path": config.asset_db_path,
        "article_count": len(report_articles),
        "all_article_count": len(all_articles),
        "new_article_count": len(new_articles),
        "articles": [_serialize_article(article) for article in report_articles],
        "new_articles": [_serialize_article(article) for article in new_articles],
        "feed_health": [_serialize_health(health) for health in health_list],
        "relevance_report": relevance_report.to_dict(),
    }
    if len(report_articles) != len(all_articles):
        data["all_articles"] = [_serialize_article(article) for article in all_articles]
    return data


def _write_json(payload: Dict[str, Any], output_path: str, label: str = "JSON 输出") -> None:
    """将结构化数据导出为 JSON，便于对接外部系统。"""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    logger.info(f"{label}已写入: {output_path}")


def _archive_run(
    config: TechBlogMonitorConfig,
    report: str,
    payload: Dict[str, Any],
    generated_at: datetime,
) -> None:
    if not config.archive_dir:
        return

    if config.archive_granularity == "week":
        iso_year, iso_week, _ = generated_at.isocalendar()
        group_dir = Path(config.archive_dir) / "weekly" / f"{iso_year}-W{iso_week:02d}"
    else:
        group_dir = Path(config.archive_dir) / "daily" / generated_at.strftime("%Y-%m-%d")

    group_dir.mkdir(parents=True, exist_ok=True)
    stamp = generated_at.strftime("%Y%m%d_%H%M%S")
    md_path = group_dir / f"tech_blog_{stamp}.md"
    json_path = group_dir / f"tech_blog_{stamp}.json"

    md_path.write_text(report, encoding="utf-8")
    _write_json(payload, str(json_path), label="归档 JSON ")

    latest_md = Path(config.archive_dir) / "latest.md"
    latest_json = Path(config.archive_dir) / "latest.json"
    latest_md.parent.mkdir(parents=True, exist_ok=True)
    latest_md.write_text(report, encoding="utf-8")
    _write_json(payload, str(latest_json), label="归档 latest JSON ")
    logger.info(f"历史归档已写入: {md_path}")


def _build_observer(config: TechBlogMonitorConfig, observer: Any | None) -> Any:
    if observer is not None:
        return observer

    try:
        registry = configure_default_metrics_registry(
            exporter=config.observability_exporter,
            endpoint=config.otlp_endpoint,
        )
    except Exception as exc:
        logger.warning("metrics exporter 初始化失败，降级为本地 registry: {}", exc)
        registry = configure_default_metrics_registry(exporter="none", endpoint="")

    observers: list[Any] = [MetricsObserver(registry)]
    if config.observability_jsonl_path:
        observers.append(JsonlObserver(config.observability_jsonl_path))
    if config.observability_exporter == "otlp":
        try:
            observers.append(
                TracingObserver(
                    build_tracing_bridge(
                        exporter=config.observability_exporter,
                        endpoint=config.otlp_endpoint,
                    )
                )
            )
        except Exception as exc:
            logger.warning("OTLP tracing 初始化失败，降级为本地 observer: {}", exc)

    if len(observers) == 1:
        return observers[0]
    return CompositeObserver(observers)


def _count_values(items: list[Any], attr_name: str) -> dict[str, int]:
    counter = Counter(str(getattr(item, attr_name, "")) for item in items if getattr(item, attr_name, ""))
    return dict(counter)


def _count_mapping_values(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    counter = Counter(str(item.get(key, "")) for item in items if item.get(key, ""))
    return dict(counter)


def _build_stage_timing_summary(run_context: RunContext) -> dict[str, dict[str, Any]]:
    return {
        outcome.stage_name: {
            "status": outcome.status,
            "duration_ms": outcome.duration_ms,
            "error_code": outcome.error_code,
            "error_message": outcome.error_message,
            "dimensions": dict(outcome.dimensions),
        }
        for outcome in run_context.stage_outcomes
    }


def _build_run_summary(
    *,
    run_context: RunContext,
    health_list: list[FeedHealth],
    all_articles: list[Article],
    analyzed_articles: list[Article],
    deliveries: list[dict[str, Any]],
) -> dict[str, Any]:
    disabled_count = sum(1 for health in health_list if health.error == "disabled")
    success_count = sum(1 for health in health_list if health.success)
    failure_count = max(len(health_list) - success_count - disabled_count, 0)
    return {
        "stage_timings": _build_stage_timing_summary(run_context),
        "feed_stats": {
            "total": len(health_list),
            "success": success_count,
            "failure": failure_count,
            "disabled": disabled_count,
        },
        "content_status_counts": _count_values(all_articles, "content_status"),
        "enrichment_status_counts": _count_values(analyzed_articles, "enrichment_status"),
        "delivery_status_counts": _count_mapping_values(deliveries, "status"),
    }


def run(
    config: Optional[TechBlogMonitorConfig] = None,
    *,
    observer: Any | None = None,
    task_id: str = "",
    task_type: str = "monitor_run",
) -> int:
    """执行博客监控并写入报告文件，返回 exit code。"""
    config = config or TechBlogMonitorConfig.from_env()
    run_context = RunContext(
        observer=_build_observer(config, observer),
        task_id=task_id,
        task_type=task_type,
        dimensions={
            "view": config.view,
            "incremental_mode": config.incremental_mode,
            "fetch_content": config.fetch_content,
            "observability_exporter": config.observability_exporter,
        },
    )
    exit_code = 1
    report = ""
    payload: Dict[str, Any] = {}
    generated_at = datetime.now(_UTC)
    all_articles: list[Article] = []
    report_articles: list[Article] = []
    analyzed_articles: list[Article] = []
    health_list: list[FeedHealth] = []
    deliveries: list[dict[str, Any]] = []
    relevance_report = RelevanceReport(
        status="skipped",
        summary="未配置技术栈画像或 repo manifest，已跳过 internal relevance。",
        signal_count=0,
        dependency_signal_count=0,
        topic_signal_count=0,
    )
    run_id = ""
    run_error: Exception | None = None
    final_error_code = ""
    final_error_message = ""

    # 0. 配置校验
    errors = config.validate()
    if errors:
        for e in errors:
            logger.error(f"配置错误: {e}")
        summary = _build_run_summary(
            run_context=run_context,
            health_list=health_list,
            all_articles=all_articles,
            analyzed_articles=analyzed_articles,
            deliveries=deliveries,
        )
        run_context.finish(
            status="failed",
            summary=summary,
            error_code="ConfigValidationError",
            error_message="; ".join(errors),
        )
        return 1

    new_urls: set[str] = set()
    store: Optional[ArticleStateStore] = None
    trend_md = ""
    temp_asset_dir: TemporaryDirectory[str] | None = None
    archive_db_path = config.asset_db_path

    try:
        with run_context.stage("fetch_feeds"):
            all_articles, health_list = fetch_all(config, run_context=run_context)

        if not all_articles:
            logger.warning("未抓取到任何文章")
            run_context.record_stage_skip("fetch_content", dimensions={"reason": "no_articles"})
            run_context.record_stage_skip("analyze_articles", dimensions={"reason": "no_articles"})
            run_context.record_stage_skip("evaluate_relevance", dimensions={"reason": "no_articles"})
            run_context.record_stage_skip("write_report", dimensions={"reason": "no_articles"})
            run_context.record_stage_skip("archive_assets", dimensions={"reason": "no_articles"})
            run_context.record_stage_skip("mirror_database", dimensions={"reason": "no_articles"})
            run_context.record_stage_skip("dispatch_deliveries", dimensions={"reason": "no_articles"})
            summary = _build_run_summary(
                run_context=run_context,
                health_list=health_list,
                all_articles=all_articles,
                analyzed_articles=analyzed_articles,
                deliveries=deliveries,
            )
            run_context.finish(
                status="failed",
                summary=summary,
                error_code="NoArticles",
                error_message="未抓取到任何文章",
            )
            return 1

        # 2. 增量状态：计算新增 URL
        if config.state_path:
            store = ArticleStateStore(config.state_path)
            all_urls = {article.url for article in all_articles}
            new_urls = store.new_urls(all_urls)
            logger.info(f"增量模式：{len(new_urls)}/{len(all_articles)} 篇为新增")

        # 3. 根据增量模式确定报告范围
        report_articles = all_articles
        if config.incremental_mode == "new_only":
            report_articles = [article for article in all_articles if article.url in new_urls]
            logger.info(
                f"仅输出新增文章模式：{len(report_articles)}/{len(all_articles)} 篇进入报告"
            )

        # 4. 正文抓取
        if config.fetch_content:
            with run_context.stage("fetch_content"):
                all_articles = fetch_contents(
                    all_articles,
                    workers=config.content_workers,
                    timeout=config.content_timeout,
                    max_chars=config.content_max_chars,
                    content_extractor=config.content_extractor,
                    playwright_fallback=config.playwright_fallback,
                    playwright_timeout=config.playwright_timeout,
                    playwright_workers=config.playwright_workers,
                )
            if config.incremental_mode == "new_only":
                report_articles = [article for article in all_articles if article.url in new_urls]
            else:
                report_articles = all_articles
        else:
            run_context.record_stage_skip(
                "fetch_content",
                dimensions={"reason": "fetch_content_disabled"},
            )

        # 5. AI 分析
        if report_articles:
            with run_context.stage("analyze_articles"):
                report_articles, trend_md = analyze(report_articles, backend=config.ai_backend)
        else:
            run_context.record_stage_skip("analyze_articles", dimensions={"reason": "no_report_articles"})
        analyzed_articles = report_articles

        if config.stack_profile_path or config.stack_repo_roots:
            try:
                with run_context.stage("evaluate_relevance"):
                    profile = load_stack_profile(config.stack_profile_path)
                    scan_result = scan_repo_roots(config.stack_repo_roots)
                    combined_warnings = [*profile.warnings, *scan_result.warnings]
                    all_articles, relevance_report = evaluate_internal_relevance(
                        all_articles,
                        profile=profile,
                        scanned_signals=scan_result.signals,
                        scanned_repo_roots=config.stack_repo_roots,
                        scanned_manifest_count=len(scan_result.scanned_files),
                        warnings=combined_warnings,
                    )
            except Exception as exc:
                logger.warning("internal relevance 失败，降级为跳过: {}", exc)
                relevance_report = RelevanceReport(
                    status="skipped",
                    summary="internal relevance 计算失败，已降级为跳过。",
                    signal_count=0,
                    dependency_signal_count=0,
                    topic_signal_count=0,
                    scanned_repo_roots=[root for root in config.stack_repo_roots if root],
                    scanned_manifest_count=0,
                    article_count=len(all_articles),
                    matched_article_count=0,
                    level_counts={},
                    top_matches=[],
                    warnings=[str(exc)],
                )
        else:
            run_context.record_stage_skip(
                "evaluate_relevance",
                dimensions={"reason": "relevance_not_configured"},
            )

        if report_articles:
            report_article_lookup = {article.url: article for article in all_articles}
            report_articles = [
                report_article_lookup.get(article.url, article)
                for article in report_articles
            ]

        # 6. 渲染报告 + 7. 写入 Markdown 报告
        with run_context.stage("write_report"):
            report = build_report(
                report_articles,
                trend_md,
                health_list,
                new_urls=new_urls if store is not None else None,
                view=config.view,
                incremental_mode=config.incremental_mode,
                relevance_report=relevance_report,
            )

            Path(config.output_path).parent.mkdir(parents=True, exist_ok=True)
            with open(config.output_path, "w", encoding="utf-8") as f:
                f.write(report)
            logger.info(f"报告已写入: {config.output_path}（{len(report_articles)} 篇文章）")

            generated_at = datetime.now(_UTC)
            payload = _build_json_payload(
                config=config,
                all_articles=all_articles,
                report_articles=report_articles,
                health_list=health_list,
                new_urls=new_urls,
                generated_at=generated_at,
                relevance_report=relevance_report,
            )

        # 8. Phase 1 历史资产存储
        if not archive_db_path and config.database_url:
            temp_asset_dir = TemporaryDirectory(prefix="tech_blog_monitor_assets_")
            archive_db_path = str(Path(temp_asset_dir.name) / "assets.db")

        if archive_db_path:
            with run_context.stage("archive_assets"):
                with ArchiveStore(archive_db_path) as archive_store:
                    run_id = archive_store.record_run(
                        generated_at=int(generated_at.timestamp()),
                        generated_at_iso=generated_at.isoformat(),
                        output_path=config.output_path,
                        view=config.view,
                        incremental_mode=config.incremental_mode,
                        all_articles=all_articles,
                        report_articles=report_articles,
                        new_urls=new_urls,
                    )
                run_context.asset_run_id = run_id
                payload["run_id"] = run_id
                if config.asset_db_path:
                    logger.info(f"历史资产已写入: {config.asset_db_path}（run_id={run_id}）")
        else:
            run_context.record_stage_skip("archive_assets", dimensions={"reason": "asset_db_not_configured"})

        if config.database_url and archive_db_path:
            with run_context.stage("mirror_database"):
                mirror_sqlite_asset_db(archive_db_path, config.database_url)
                logger.info(f"数据库资产已同步: {config.database_url}（run_id={run_id}）")
        else:
            run_context.record_stage_skip(
                "mirror_database",
                dimensions={"reason": "database_url_not_configured"},
            )

        # 8.1 Phase 7 产品化分发
        if (
            run_id
            and config.asset_db_path
            and config.delivery_webhook_url
            and config.delivery_roles
        ):
            with run_context.stage("dispatch_deliveries"):
                insight_report = analyze_insights(
                    config.asset_db_path,
                    InsightQuery(anchor_ts=int(generated_at.timestamp()) + 1),
                )
                deliveries = maybe_dispatch_deliveries(
                    db_path=config.asset_db_path,
                    request=DeliveryRequest(
                        run_id=run_id,
                        generated_at=int(generated_at.timestamp()),
                        cadence=config.delivery_cadence,
                        webhook_url=config.delivery_webhook_url,
                        roles=config.delivery_roles,
                        max_retries=config.delivery_max_retries,
                        rate_limit_per_minute=config.delivery_rate_limit_per_minute,
                    ),
                    report_markdown=report,
                    articles=report_articles,
                    insight_report=insight_report,
                    run_context=run_context,
                )
                payload["deliveries"] = deliveries
                logger.info(f"产品化分发已处理 {len(deliveries)} 条")
        else:
            run_context.record_stage_skip(
                "dispatch_deliveries",
                dimensions={"reason": "delivery_not_configured"},
            )

        summary = _build_run_summary(
            run_context=run_context,
            health_list=health_list,
            all_articles=all_articles,
            analyzed_articles=analyzed_articles,
            deliveries=deliveries,
        )
        payload["run_summary"] = run_context.compose_summary(status="success", summary=summary)

        # 9. JSON 输出
        if config.json_output_path:
            _write_json(payload, config.json_output_path)

        # 10. 历史归档
        _archive_run(config, report, payload, generated_at)

        # 11. 更新增量状态
        if store is not None:
            now_ts = int(generated_at.timestamp())
            for article in all_articles:
                store.mark_article(article, now_ts)
            expired = store.expire(config.state_max_age_days)
            store.save()
            if expired:
                logger.info(f"状态文件已清理 {expired} 条过期记录")
            logger.info(f"状态文件已更新: {config.state_path}（共 {len(store)} 条记录）")

        final_summary = run_context.finish(status="success", summary=summary)
        payload["run_summary"] = final_summary
        exit_code = 0
    except Exception as exc:
        run_error = exc
        final_error_code = exc.__class__.__name__
        final_error_message = str(exc)
        summary = _build_run_summary(
            run_context=run_context,
            health_list=health_list,
            all_articles=all_articles,
            analyzed_articles=analyzed_articles,
            deliveries=deliveries,
        )
        if payload:
            payload["run_summary"] = run_context.compose_summary(
                status="failed",
                summary=summary,
                error_code=final_error_code,
                error_message=final_error_message,
            )
        run_context.finish(
            status="failed",
            summary=summary,
            error_code=final_error_code,
            error_message=final_error_message,
        )
    finally:
        if temp_asset_dir is not None:
            temp_asset_dir.cleanup()

    if run_error is not None:
        raise run_error

    print(report)
    return exit_code
