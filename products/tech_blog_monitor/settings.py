"""Tech Blog Monitor settings model。"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class TechBlogMonitorSettings(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=True, extra="ignore")

    output_path: str | None = Field(default=None, validation_alias="TECH_BLOG_OUTPUT")
    max_articles_per_feed: str | None = Field(default=None, validation_alias="TECH_BLOG_MAX_ARTICLES")
    max_age_days: str | None = Field(default=None, validation_alias="TECH_BLOG_MAX_AGE_DAYS")
    max_total_articles: str | None = Field(default=None, validation_alias="TECH_BLOG_MAX_TOTAL")
    max_articles_per_source: str | None = Field(default=None, validation_alias="TECH_BLOG_MAX_PER_SOURCE")
    fetch_workers: str | None = Field(default=None, validation_alias="TECH_BLOG_FETCH_WORKERS")
    fetch_content: str | None = Field(default=None, validation_alias="TECH_BLOG_FETCH_CONTENT")
    content_timeout: str | None = Field(default=None, validation_alias="TECH_BLOG_CONTENT_TIMEOUT")
    content_workers: str | None = Field(default=None, validation_alias="TECH_BLOG_CONTENT_WORKERS")
    content_max_chars: str | None = Field(default=None, validation_alias="TECH_BLOG_CONTENT_MAX_CHARS")
    content_extractor: str | None = Field(
        default=None,
        validation_alias="TECH_BLOG_CONTENT_EXTRACTOR",
    )
    playwright_fallback: str | None = Field(
        default=None,
        validation_alias="TECH_BLOG_PLAYWRIGHT_FALLBACK",
    )
    playwright_timeout: str | None = Field(
        default=None,
        validation_alias="TECH_BLOG_PLAYWRIGHT_TIMEOUT",
    )
    playwright_workers: str | None = Field(
        default=None,
        validation_alias="TECH_BLOG_PLAYWRIGHT_WORKERS",
    )
    view: str | None = Field(default=None, validation_alias="TECH_BLOG_VIEW")
    feeds_yaml: str | None = Field(default=None, validation_alias="TECH_BLOG_FEEDS_YAML")
    incremental_mode: str | None = Field(default=None, validation_alias="TECH_BLOG_INCREMENTAL_MODE")
    state_path: str | None = Field(default=None, validation_alias="TECH_BLOG_STATE_PATH")
    state_max_age_days: str | None = Field(
        default=None,
        validation_alias="TECH_BLOG_STATE_MAX_AGE_DAYS",
    )
    json_output_path: str | None = Field(default=None, validation_alias="TECH_BLOG_JSON_OUTPUT")
    archive_dir: str | None = Field(default=None, validation_alias="TECH_BLOG_ARCHIVE_DIR")
    archive_granularity: str | None = Field(
        default=None,
        validation_alias="TECH_BLOG_ARCHIVE_GRANULARITY",
    )
    asset_db_path: str | None = Field(default=None, validation_alias="TECH_BLOG_ASSET_DB_PATH")
    database_url: str | None = Field(default=None, validation_alias="TECH_BLOG_DATABASE_URL")
    observability_jsonl_path: str | None = Field(
        default=None,
        validation_alias="TECH_BLOG_OBSERVABILITY_JSONL",
    )
    observability_exporter: str | None = Field(
        default=None,
        validation_alias="TECH_BLOG_OBSERVABILITY_EXPORTER",
    )
    otlp_endpoint: str | None = Field(
        default=None,
        validation_alias="TECH_BLOG_OTLP_ENDPOINT",
    )
    orchestration_mode: str | None = Field(
        default=None,
        validation_alias="TECH_BLOG_ORCHESTRATION_MODE",
    )
    prefect_deployment_name: str | None = Field(
        default=None,
        validation_alias="TECH_BLOG_PREFECT_DEPLOYMENT_NAME",
    )
    ai_backend: str | None = Field(default=None, validation_alias="AGENT_RUNTIME")
    delivery_webhook_url: str | None = Field(
        default=None,
        validation_alias="TECH_BLOG_DELIVERY_WEBHOOK",
    )
    delivery_roles: str | None = Field(default=None, validation_alias="TECH_BLOG_DELIVERY_ROLES")
    delivery_cadence: str | None = Field(
        default=None,
        validation_alias="TECH_BLOG_DELIVERY_CADENCE",
    )
    delivery_rate_limit_per_minute: str | None = Field(
        default=None,
        validation_alias="TECH_BLOG_DELIVERY_RATE_LIMIT",
    )
    delivery_max_retries: str | None = Field(
        default=None,
        validation_alias="TECH_BLOG_DELIVERY_MAX_RETRIES",
    )
    stack_profile_path: str | None = Field(
        default=None,
        validation_alias="TECH_BLOG_STACK_PROFILE_PATH",
    )
    stack_repo_roots: str | None = Field(
        default=None,
        validation_alias="TECH_BLOG_STACK_REPO_ROOTS",
    )
