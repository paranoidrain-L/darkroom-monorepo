"""Tech Blog Monitor 配置加载与类型转换。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import yaml

from products.tech_blog_monitor.defaults import DEFAULT_FEED_TIMEOUT
from products.tech_blog_monitor.feed_catalog import FeedSource


def _parse_int_value(env_key: str, raw: str | None, default: int) -> tuple[int, str | None]:
    if raw is None:
        return default, None
    try:
        return int(raw), None
    except ValueError:
        return default, f"{env_key}={raw!r} 不是合法整数，已使用默认值 {default}"


def _parse_bool_value(env_key: str, raw: str | None, default: bool) -> tuple[bool, str | None]:
    if raw is None:
        return default, None

    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True, None
    if normalized in {"0", "false", "no", "off"}:
        return False, None
    return default, f"{env_key}={raw!r} 不是合法布尔值，已使用默认值 {default}"


def _parse_int(env_key: str, default: int) -> tuple[int, str | None]:
    return _parse_int_value(env_key, os.environ.get(env_key), default)


def _parse_bool(env_key: str, default: bool) -> tuple[bool, str | None]:
    return _parse_bool_value(env_key, os.environ.get(env_key), default)


def _load_feeds_from_yaml(path: str) -> tuple[list[FeedSource], list[str]]:
    errors: list[str] = []

    if not os.path.exists(path):
        return [], [f"YAML 文件不存在: {path}"]

    try:
        with open(path, encoding="utf-8") as file:
            data = yaml.safe_load(file)
    except yaml.YAMLError as exc:
        return [], [f"YAML 解析失败 ({path}): {exc}"]

    if not data:
        return [], [f"YAML 文件为空: {path}"]

    if not isinstance(data, dict) or "feeds" not in data:
        return [], [f"YAML 缺少顶层 'feeds' 键: {path}"]

    raw_feeds = data["feeds"]
    if not isinstance(raw_feeds, list):
        return [], [f"YAML 'feeds' 必须是列表: {path}"]

    feeds: list[FeedSource] = []
    for index, item in enumerate(raw_feeds):
        if not isinstance(item, dict):
            errors.append(f"feeds[{index}] 不是字典，已跳过")
            continue

        name = item.get("name")
        url = item.get("url")
        if not name or not isinstance(name, str):
            errors.append(f"feeds[{index}] 缺少必填字段 'name' 或类型不是字符串，已跳过")
            continue
        if not url or not isinstance(url, str):
            errors.append(
                f"feeds[{index}] ({name!r}) 缺少必填字段 'url' 或类型不是字符串，已跳过"
            )
            continue

        timeout = item.get("timeout", DEFAULT_FEED_TIMEOUT)
        if not isinstance(timeout, int):
            errors.append(
                f"feeds[{index}] ({name!r}) timeout 必须是整数，已使用默认值 {DEFAULT_FEED_TIMEOUT}"
            )
            timeout = DEFAULT_FEED_TIMEOUT

        verify_ssl = item.get("verify_ssl", True)
        if not isinstance(verify_ssl, bool):
            errors.append(f"feeds[{index}] ({name!r}) verify_ssl 必须是布尔值，已使用默认值 true")
            verify_ssl = True

        headers = item.get("headers", {})
        if not isinstance(headers, dict):
            errors.append(f"feeds[{index}] ({name!r}) headers 必须是字典，已使用空字典")
            headers = {}

        enabled = item.get("enabled", True)
        if not isinstance(enabled, bool):
            errors.append(f"feeds[{index}] ({name!r}) enabled 必须是布尔值，已使用默认值 true")
            enabled = True

        source_type = item.get("source_type", "rss")
        if not isinstance(source_type, str) or not source_type.strip():
            errors.append(f"feeds[{index}] ({name!r}) source_type 必须是非空字符串，已使用默认值 rss")
            source_type = "rss"

        metadata = item.get("metadata", {})
        if not isinstance(metadata, dict):
            errors.append(f"feeds[{index}] ({name!r}) metadata 必须是字典，已使用空字典")
            metadata = {}

        feeds.append(
            FeedSource(
                name=name,
                url=url,
                category=item.get("category", "未分类"),
                timeout=timeout,
                verify_ssl=verify_ssl,
                headers=headers,
                enabled=enabled,
                source_type=source_type.strip().lower(),
                metadata=metadata,
            )
        )

    return feeds, errors


@dataclass
class LoadedConfigValues:
    values: dict[str, Any]
    parse_errors: list[str]


def load_settings_overrides(settings: Any, *, current: Any) -> LoadedConfigValues:
    values: dict[str, Any] = {}
    parse_errors: list[str] = []

    if settings.output_path is not None:
        values["output_path"] = settings.output_path
    if settings.ai_backend is not None:
        values["ai_backend"] = settings.ai_backend
    if settings.view is not None:
        values["view"] = settings.view

    integer_fields = [
        ("max_articles_per_feed", "TECH_BLOG_MAX_ARTICLES"),
        ("max_age_days", "TECH_BLOG_MAX_AGE_DAYS"),
        ("max_total_articles", "TECH_BLOG_MAX_TOTAL"),
        ("max_articles_per_source", "TECH_BLOG_MAX_PER_SOURCE"),
        ("fetch_workers", "TECH_BLOG_FETCH_WORKERS"),
        ("content_timeout", "TECH_BLOG_CONTENT_TIMEOUT"),
        ("content_workers", "TECH_BLOG_CONTENT_WORKERS"),
        ("content_max_chars", "TECH_BLOG_CONTENT_MAX_CHARS"),
        ("playwright_timeout", "TECH_BLOG_PLAYWRIGHT_TIMEOUT"),
        ("playwright_workers", "TECH_BLOG_PLAYWRIGHT_WORKERS"),
        ("state_max_age_days", "TECH_BLOG_STATE_MAX_AGE_DAYS"),
        ("delivery_rate_limit_per_minute", "TECH_BLOG_DELIVERY_RATE_LIMIT"),
        ("delivery_max_retries", "TECH_BLOG_DELIVERY_MAX_RETRIES"),
    ]
    for field_name, env_key in integer_fields:
        value, error = _parse_int_value(env_key, getattr(settings, field_name), getattr(current, field_name))
        values[field_name] = value
        if error:
            parse_errors.append(error)

    fetch_content, error = _parse_bool_value(
        "TECH_BLOG_FETCH_CONTENT",
        settings.fetch_content,
        current.fetch_content,
    )
    values["fetch_content"] = fetch_content
    if error:
        parse_errors.append(error)

    playwright_fallback, error = _parse_bool_value(
        "TECH_BLOG_PLAYWRIGHT_FALLBACK",
        settings.playwright_fallback,
        current.playwright_fallback,
    )
    values["playwright_fallback"] = playwright_fallback
    if error:
        parse_errors.append(error)

    string_fields = [
        "content_extractor",
        "state_path",
        "incremental_mode",
        "json_output_path",
        "archive_dir",
        "archive_granularity",
        "asset_db_path",
        "database_url",
        "observability_jsonl_path",
        "observability_exporter",
        "otlp_endpoint",
        "orchestration_mode",
        "prefect_deployment_name",
        "delivery_webhook_url",
        "delivery_cadence",
        "stack_profile_path",
    ]
    for field_name in string_fields:
        raw = getattr(settings, field_name)
        if raw is not None:
            values[field_name] = raw

    if settings.delivery_roles and settings.delivery_roles.strip():
        values["delivery_roles"] = [
            role.strip() for role in settings.delivery_roles.split(",") if role.strip()
        ]

    if settings.stack_repo_roots is not None:
        values["stack_repo_roots"] = [
            path.strip()
            for path in settings.stack_repo_roots.split(",")
            if path.strip()
        ]

    if settings.feeds_yaml:
        feeds, yaml_errors = _load_feeds_from_yaml(settings.feeds_yaml)
        parse_errors.extend(yaml_errors)
        if feeds:
            values["feeds"] = feeds

    return LoadedConfigValues(values=values, parse_errors=parse_errors)
