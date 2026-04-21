"""Tech Blog Monitor 配置兼容层。"""

from __future__ import annotations

from dataclasses import dataclass, field

from products.tech_blog_monitor.config_loader import (
    _load_feeds_from_yaml as _load_feeds_from_yaml_impl,
)
from products.tech_blog_monitor.config_loader import (
    _parse_bool as _parse_bool_impl,
)
from products.tech_blog_monitor.config_loader import (
    _parse_int as _parse_int_impl,
)
from products.tech_blog_monitor.config_loader import (
    load_settings_overrides,
)
from products.tech_blog_monitor.config_validator import validate_config
from products.tech_blog_monitor.defaults import (
    DEFAULT_AI_BACKEND,
    DEFAULT_ARCHIVE_DIR,
    DEFAULT_ARCHIVE_GRANULARITY,
    DEFAULT_ASSET_DB_PATH,
    DEFAULT_CONTENT_EXTRACTOR,
    DEFAULT_CONTENT_MAX_CHARS,
    DEFAULT_CONTENT_TIMEOUT,
    DEFAULT_CONTENT_WORKERS,
    DEFAULT_DATABASE_URL,
    DEFAULT_DELIVERY_CADENCE,
    DEFAULT_DELIVERY_MAX_RETRIES,
    DEFAULT_DELIVERY_RATE_LIMIT_PER_MINUTE,
    DEFAULT_DELIVERY_WEBHOOK_URL,
    DEFAULT_FETCH_CONTENT,
    DEFAULT_FETCH_WORKERS,
    DEFAULT_INCREMENTAL_MODE,
    DEFAULT_JSON_OUTPUT_PATH,
    DEFAULT_MAX_AGE_DAYS,
    DEFAULT_MAX_ARTICLES_PER_FEED,
    DEFAULT_MAX_ARTICLES_PER_SOURCE,
    DEFAULT_MAX_TOTAL_ARTICLES,
    DEFAULT_OBSERVABILITY_EXPORTER,
    DEFAULT_OBSERVABILITY_JSONL_PATH,
    DEFAULT_ORCHESTRATION_MODE,
    DEFAULT_OTLP_ENDPOINT,
    DEFAULT_OUTPUT_PATH,
    DEFAULT_PLAYWRIGHT_FALLBACK,
    DEFAULT_PLAYWRIGHT_TIMEOUT,
    DEFAULT_PLAYWRIGHT_WORKERS,
    DEFAULT_PREFECT_DEPLOYMENT_NAME,
    DEFAULT_SCHEDULE_TIMES,
    DEFAULT_STACK_PROFILE_PATH,
    DEFAULT_STACK_REPO_ROOTS,
    DEFAULT_STATE_MAX_AGE_DAYS,
    DEFAULT_STATE_PATH,
    DEFAULT_VIEW,
)
from products.tech_blog_monitor.feed_catalog import DEFAULT_FEEDS, FeedSource
from products.tech_blog_monitor.settings import TechBlogMonitorSettings

_parse_int = _parse_int_impl
_parse_bool = _parse_bool_impl
_load_feeds_from_yaml = _load_feeds_from_yaml_impl


@dataclass
class TechBlogMonitorConfig:
    feeds: list[FeedSource] = field(default_factory=lambda: list(DEFAULT_FEEDS))
    max_articles_per_feed: int = DEFAULT_MAX_ARTICLES_PER_FEED
    max_age_days: int = DEFAULT_MAX_AGE_DAYS
    max_total_articles: int = DEFAULT_MAX_TOTAL_ARTICLES
    max_articles_per_source: int = DEFAULT_MAX_ARTICLES_PER_SOURCE
    fetch_workers: int = DEFAULT_FETCH_WORKERS
    fetch_content: bool = DEFAULT_FETCH_CONTENT
    content_timeout: int = DEFAULT_CONTENT_TIMEOUT
    content_workers: int = DEFAULT_CONTENT_WORKERS
    content_max_chars: int = DEFAULT_CONTENT_MAX_CHARS
    content_extractor: str = DEFAULT_CONTENT_EXTRACTOR
    playwright_fallback: bool = DEFAULT_PLAYWRIGHT_FALLBACK
    playwright_timeout: int = DEFAULT_PLAYWRIGHT_TIMEOUT
    playwright_workers: int = DEFAULT_PLAYWRIGHT_WORKERS
    output_path: str = DEFAULT_OUTPUT_PATH
    ai_backend: str = DEFAULT_AI_BACKEND
    schedule_times: list[str] = field(default_factory=lambda: list(DEFAULT_SCHEDULE_TIMES))
    keyword_filters: dict[str, list[str]] = field(default_factory=dict)
    view: str = DEFAULT_VIEW
    state_path: str = DEFAULT_STATE_PATH
    state_max_age_days: int = DEFAULT_STATE_MAX_AGE_DAYS
    incremental_mode: str = DEFAULT_INCREMENTAL_MODE
    json_output_path: str = DEFAULT_JSON_OUTPUT_PATH
    archive_dir: str = DEFAULT_ARCHIVE_DIR
    archive_granularity: str = DEFAULT_ARCHIVE_GRANULARITY
    asset_db_path: str = DEFAULT_ASSET_DB_PATH
    database_url: str = DEFAULT_DATABASE_URL
    observability_jsonl_path: str = DEFAULT_OBSERVABILITY_JSONL_PATH
    observability_exporter: str = DEFAULT_OBSERVABILITY_EXPORTER
    otlp_endpoint: str = DEFAULT_OTLP_ENDPOINT
    orchestration_mode: str = DEFAULT_ORCHESTRATION_MODE
    prefect_deployment_name: str = DEFAULT_PREFECT_DEPLOYMENT_NAME
    delivery_webhook_url: str = DEFAULT_DELIVERY_WEBHOOK_URL
    delivery_roles: list[str] = field(default_factory=list)
    delivery_cadence: str = DEFAULT_DELIVERY_CADENCE
    delivery_rate_limit_per_minute: int = DEFAULT_DELIVERY_RATE_LIMIT_PER_MINUTE
    delivery_max_retries: int = DEFAULT_DELIVERY_MAX_RETRIES
    stack_profile_path: str = DEFAULT_STACK_PROFILE_PATH
    stack_repo_roots: list[str] = field(default_factory=lambda: list(DEFAULT_STACK_REPO_ROOTS))
    _parse_errors: list[str] = field(default_factory=list, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        settings = TechBlogMonitorSettings()
        loaded = load_settings_overrides(settings, current=self)
        self._parse_errors = list(loaded.parse_errors)
        for field_name, value in loaded.values.items():
            setattr(self, field_name, value)

    @classmethod
    def from_env(cls) -> "TechBlogMonitorConfig":
        return cls()

    def validate(self) -> list[str]:
        return validate_config(self, self._parse_errors)
