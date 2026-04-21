"""Tech Blog Monitor 配置校验。"""

from __future__ import annotations

from typing import Any, Sequence

from products.tech_blog_monitor.defaults import (
    ALLOWED_ARCHIVE_GRANULARITIES,
    ALLOWED_CONTENT_EXTRACTORS,
    ALLOWED_DELIVERY_CADENCES,
    ALLOWED_DELIVERY_ROLES,
    ALLOWED_INCREMENTAL_MODES,
    ALLOWED_OBSERVABILITY_EXPORTERS,
    ALLOWED_ORCHESTRATION_MODES,
    ALLOWED_VIEWS,
)


def validate_config(config: Any, parse_errors: Sequence[str]) -> list[str]:
    errors = list(parse_errors)

    if config.max_articles_per_feed < 1:
        errors.append(f"max_articles_per_feed={config.max_articles_per_feed} 必须 >= 1")
    if config.max_age_days < 0:
        errors.append(f"max_age_days={config.max_age_days} 必须 >= 0（0 表示不过滤）")
    if config.max_total_articles < 0:
        errors.append(f"max_total_articles={config.max_total_articles} 必须 >= 0（0 表示不限制）")
    if config.max_articles_per_source < 0:
        errors.append(
            f"max_articles_per_source={config.max_articles_per_source} 必须 >= 0（0 表示不限制）"
        )
    if config.fetch_workers < 1:
        errors.append(f"fetch_workers={config.fetch_workers} 必须 >= 1")
    if config.content_timeout < 1:
        errors.append(f"content_timeout={config.content_timeout} 必须 >= 1")
    if config.content_workers < 1:
        errors.append(f"content_workers={config.content_workers} 必须 >= 1")
    if config.content_max_chars < 1:
        errors.append(f"content_max_chars={config.content_max_chars} 必须 >= 1")
    if config.playwright_timeout < 1:
        errors.append(f"playwright_timeout={config.playwright_timeout} 必须 >= 1")
    if config.playwright_workers < 1:
        errors.append(f"playwright_workers={config.playwright_workers} 必须 >= 1")
    if config.state_max_age_days < 0:
        errors.append(f"state_max_age_days={config.state_max_age_days} 必须 >= 0（0 表示不过期）")
    if config.content_extractor not in ALLOWED_CONTENT_EXTRACTORS:
        errors.append(
            f"content_extractor={config.content_extractor!r} 必须为 'trafilatura' 或 'heuristic'"
        )
    if config.observability_exporter not in ALLOWED_OBSERVABILITY_EXPORTERS:
        errors.append(
            "observability_exporter="
            f"{config.observability_exporter!r} 必须为 'none'、'jsonl' 或 'otlp'"
        )
    if config.orchestration_mode not in ALLOWED_ORCHESTRATION_MODES:
        errors.append(
            "orchestration_mode="
            f"{config.orchestration_mode!r} 必须为 'local' 或 'prefect'"
        )
    if config.view not in ALLOWED_VIEWS:
        errors.append(f"view={config.view!r} 必须为 'by_category' 或 'by_time'")
    if config.incremental_mode not in ALLOWED_INCREMENTAL_MODES:
        errors.append(f"incremental_mode={config.incremental_mode!r} 必须为 'split' 或 'new_only'")
    if config.incremental_mode == "new_only" and not config.state_path:
        errors.append("incremental_mode='new_only' 需要同时配置 state_path")
    if config.archive_granularity not in ALLOWED_ARCHIVE_GRANULARITIES:
        errors.append(f"archive_granularity={config.archive_granularity!r} 必须为 'day' 或 'week'")
    if config.delivery_cadence not in ALLOWED_DELIVERY_CADENCES:
        errors.append(f"delivery_cadence={config.delivery_cadence!r} 必须为 'daily' 或 'weekly'")
    if config.delivery_rate_limit_per_minute < 1:
        errors.append(
            f"delivery_rate_limit_per_minute={config.delivery_rate_limit_per_minute} 必须 >= 1"
        )
    if config.delivery_max_retries < 1:
        errors.append(f"delivery_max_retries={config.delivery_max_retries} 必须 >= 1")

    invalid_roles = [role for role in config.delivery_roles if role not in ALLOWED_DELIVERY_ROLES]
    if invalid_roles:
        errors.append(f"delivery_roles 包含不支持的角色: {', '.join(invalid_roles)}")
    if config.delivery_roles and not config.delivery_webhook_url:
        errors.append("配置 delivery_roles 时需要同时配置 delivery_webhook_url")
    if config.delivery_webhook_url and not config.asset_db_path:
        errors.append("启用 delivery_webhook_url 时需要同时配置 asset_db_path")
    if config.observability_exporter == "jsonl" and not config.observability_jsonl_path:
        errors.append("observability_exporter='jsonl' 需要同时配置 observability_jsonl_path")
    if not isinstance(config.stack_repo_roots, list):
        errors.append("stack_repo_roots 必须是路径列表")
    if not config.feeds:
        errors.append("feeds 列表为空，至少需要一个 RSS 源")

    return errors
