# -*- coding: utf-8 -*-
"""Tech Blog Monitor config 单元测试。"""

import textwrap

from products.tech_blog_monitor.config import (
    FeedSource,
    TechBlogMonitorConfig,
    _load_feeds_from_yaml,
    _parse_bool,
    _parse_int,
)
from products.tech_blog_monitor.settings import TechBlogMonitorSettings

# ── _parse_int ────────────────────────────────────────────────────────────────

class TestParseInt:
    def test_missing_env_returns_default(self, monkeypatch):
        monkeypatch.delenv("SOME_KEY", raising=False)
        val, err = _parse_int("SOME_KEY", 42)
        assert val == 42
        assert err is None

    def test_valid_env_returns_parsed(self, monkeypatch):
        monkeypatch.setenv("SOME_KEY", "7")
        val, err = _parse_int("SOME_KEY", 42)
        assert val == 7
        assert err is None

    def test_invalid_env_returns_default_and_error(self, monkeypatch):
        monkeypatch.setenv("SOME_KEY", "abc")
        val, err = _parse_int("SOME_KEY", 42)
        assert val == 42
        assert err is not None
        assert "SOME_KEY" in err
        assert "abc" in err


class TestParseBool:
    def test_missing_env_returns_default(self, monkeypatch):
        monkeypatch.delenv("BOOL_KEY", raising=False)
        val, err = _parse_bool("BOOL_KEY", True)
        assert val is True
        assert err is None

    def test_valid_true_env(self, monkeypatch):
        monkeypatch.setenv("BOOL_KEY", "off")
        val, err = _parse_bool("BOOL_KEY", True)
        assert val is False
        assert err is None

    def test_invalid_bool_returns_default_and_error(self, monkeypatch):
        monkeypatch.setenv("BOOL_KEY", "maybe")
        val, err = _parse_bool("BOOL_KEY", False)
        assert val is False
        assert err is not None
        assert "BOOL_KEY" in err


# ── _load_feeds_from_yaml ─────────────────────────────────────────────────────

class TestLoadFeedsFromYaml:
    def test_valid_yaml(self, tmp_path):
        f = tmp_path / "feeds.yaml"
        f.write_text(textwrap.dedent("""\
            feeds:
              - name: Test Feed
                url: https://example.com/rss
                category: 测试
        """))
        feeds, errors = _load_feeds_from_yaml(str(f))
        assert len(feeds) == 1
        assert feeds[0].name == "Test Feed"
        assert errors == []

    def test_file_not_found(self, tmp_path):
        feeds, errors = _load_feeds_from_yaml(str(tmp_path / "missing.yaml"))
        assert feeds == []
        assert any("不存在" in e for e in errors)

    def test_empty_file(self, tmp_path):
        f = tmp_path / "empty.yaml"
        f.write_text("")
        feeds, errors = _load_feeds_from_yaml(str(f))
        assert feeds == []
        assert any("为空" in e for e in errors)

    def test_missing_feeds_key(self, tmp_path):
        f = tmp_path / "bad.yaml"
        f.write_text("other_key: value\n")
        feeds, errors = _load_feeds_from_yaml(str(f))
        assert feeds == []
        assert any("feeds" in e for e in errors)

    def test_missing_name_skips_entry(self, tmp_path):
        f = tmp_path / "feeds.yaml"
        f.write_text(textwrap.dedent("""\
            feeds:
              - url: https://example.com/rss
                category: 测试
        """))
        feeds, errors = _load_feeds_from_yaml(str(f))
        assert feeds == []
        assert any("name" in e for e in errors)

    def test_missing_url_skips_entry(self, tmp_path):
        f = tmp_path / "feeds.yaml"
        f.write_text(textwrap.dedent("""\
            feeds:
              - name: Test
                category: 测试
        """))
        feeds, errors = _load_feeds_from_yaml(str(f))
        assert feeds == []
        assert any("url" in e for e in errors)

    def test_invalid_headers_type_uses_default(self, tmp_path):
        f = tmp_path / "feeds.yaml"
        f.write_text(textwrap.dedent("""\
            feeds:
              - name: Test
                url: https://example.com/rss
                category: 测试
                headers: not-a-dict
        """))
        feeds, errors = _load_feeds_from_yaml(str(f))
        assert len(feeds) == 1
        assert feeds[0].headers == {}
        assert any("headers" in e for e in errors)

    def test_invalid_verify_ssl_type_uses_default(self, tmp_path):
        f = tmp_path / "feeds.yaml"
        f.write_text(textwrap.dedent("""\
            feeds:
              - name: Test
                url: https://example.com/rss
                category: 测试
                verify_ssl: maybe
        """))
        feeds, errors = _load_feeds_from_yaml(str(f))
        assert len(feeds) == 1
        assert feeds[0].verify_ssl is True
        assert any("verify_ssl" in e for e in errors)

    def test_partial_valid_feeds(self, tmp_path):
        """有效条目正常加载，无效条目跳过并记录错误。"""
        f = tmp_path / "feeds.yaml"
        f.write_text(textwrap.dedent("""\
            feeds:
              - name: Good Feed
                url: https://good.com/rss
                category: 测试
              - url: https://bad.com/rss
                category: 测试
        """))
        feeds, errors = _load_feeds_from_yaml(str(f))
        assert len(feeds) == 1
        assert feeds[0].name == "Good Feed"
        assert len(errors) == 1

    def test_loads_metadata_for_non_rss_source(self, tmp_path):
        f = tmp_path / "feeds.yaml"
        f.write_text(textwrap.dedent("""\
            feeds:
              - name: uv Releases
                url: https://api.github.com/repos/astral-sh/uv/releases
                category: 工程实践
                source_type: github_releases
                metadata:
                  include_prereleases: false
        """))
        feeds, errors = _load_feeds_from_yaml(str(f))
        assert errors == []
        assert feeds[0].source_type == "github_releases"
        assert feeds[0].metadata == {"include_prereleases": False}

    def test_invalid_metadata_type_uses_empty_dict(self, tmp_path):
        f = tmp_path / "feeds.yaml"
        f.write_text(textwrap.dedent("""\
            feeds:
              - name: uv Releases
                url: https://api.github.com/repos/astral-sh/uv/releases
                category: 工程实践
                source_type: github_releases
                metadata: not-a-dict
        """))
        feeds, errors = _load_feeds_from_yaml(str(f))
        assert len(feeds) == 1
        assert feeds[0].metadata == {}
        assert any("metadata" in e for e in errors)


# ── TechBlogMonitorConfig ─────────────────────────────────────────────────────

class TestTechBlogMonitorSettings:
    def test_reads_raw_env_values_via_aliases(self, monkeypatch):
        monkeypatch.setenv("TECH_BLOG_MAX_ARTICLES", "7")
        monkeypatch.setenv("TECH_BLOG_FETCH_CONTENT", "false")
        monkeypatch.setenv("AGENT_RUNTIME", "codex")

        settings = TechBlogMonitorSettings()

        assert settings.max_articles_per_feed == "7"
        assert settings.fetch_content == "false"
        assert settings.ai_backend == "codex"

class TestTechBlogMonitorConfig:
    def test_loads_feeds_from_yaml(self, monkeypatch):
        yaml_path = "docs/tech_blog_monitor/feeds/rss-feeds-example.yaml"
        monkeypatch.setenv("TECH_BLOG_FEEDS_YAML", yaml_path)
        config = TechBlogMonitorConfig()
        assert len(config.feeds) > 0
        assert any(feed.verify_ssl is False for feed in config.feeds)
        assert any(feed.enabled is False for feed in config.feeds)

    def test_reads_fetch_workers_from_env(self, monkeypatch):
        monkeypatch.setenv("TECH_BLOG_FETCH_WORKERS", "7")
        config = TechBlogMonitorConfig(feeds=[FeedSource("D", "https://d.com/rss", "T")])
        assert config.fetch_workers == 7

    def test_env_override_wins_over_constructor_value(self, monkeypatch):
        monkeypatch.setenv("TECH_BLOG_FETCH_WORKERS", "7")
        config = TechBlogMonitorConfig(
            feeds=[FeedSource("D", "https://d.com/rss", "T")],
            fetch_workers=9,
        )
        assert config.fetch_workers == 7

    def test_invalid_env_falls_back_to_constructor_value(self, monkeypatch):
        monkeypatch.setenv("TECH_BLOG_FETCH_WORKERS", "abc")
        config = TechBlogMonitorConfig(
            feeds=[FeedSource("D", "https://d.com/rss", "T")],
            fetch_workers=9,
        )
        assert config.fetch_workers == 9
        assert any("默认值 9" in error for error in config._parse_errors)

    def test_reads_incremental_and_archive_settings_from_env(self, monkeypatch):
        monkeypatch.setenv("TECH_BLOG_INCREMENTAL_MODE", "new_only")
        monkeypatch.setenv("TECH_BLOG_STATE_PATH", "/tmp/state.json")
        monkeypatch.setenv("TECH_BLOG_ARCHIVE_DIR", "/tmp/archive")
        monkeypatch.setenv("TECH_BLOG_ARCHIVE_GRANULARITY", "week")
        monkeypatch.setenv("TECH_BLOG_ASSET_DB_PATH", "/tmp/assets.db")
        monkeypatch.setenv("TECH_BLOG_OBSERVABILITY_JSONL", "/tmp/observability.jsonl")
        monkeypatch.setenv("TECH_BLOG_OBSERVABILITY_EXPORTER", "jsonl")
        monkeypatch.setenv("TECH_BLOG_OTLP_ENDPOINT", "http://127.0.0.1:4318/v1/traces")
        monkeypatch.setenv("TECH_BLOG_ORCHESTRATION_MODE", "prefect")
        monkeypatch.setenv("TECH_BLOG_PREFECT_DEPLOYMENT_NAME", "demo/tech-blog")
        monkeypatch.setenv("TECH_BLOG_DELIVERY_WEBHOOK", "https://example.com/webhook")
        monkeypatch.setenv("TECH_BLOG_DELIVERY_ROLES", "executive,engineer")
        monkeypatch.setenv("TECH_BLOG_DELIVERY_CADENCE", "weekly")
        monkeypatch.setenv("TECH_BLOG_DELIVERY_RATE_LIMIT", "5")
        monkeypatch.setenv("TECH_BLOG_DELIVERY_MAX_RETRIES", "4")
        monkeypatch.setenv("TECH_BLOG_STACK_PROFILE_PATH", "/tmp/stack_profile.yaml")
        monkeypatch.setenv("TECH_BLOG_STACK_REPO_ROOTS", "/repo/a,/repo/b")
        monkeypatch.setenv("TECH_BLOG_FETCH_CONTENT", "false")
        monkeypatch.setenv("TECH_BLOG_CONTENT_TIMEOUT", "20")
        monkeypatch.setenv("TECH_BLOG_CONTENT_WORKERS", "4")
        monkeypatch.setenv("TECH_BLOG_CONTENT_MAX_CHARS", "12345")
        config = TechBlogMonitorConfig(feeds=[FeedSource("D", "https://d.com/rss", "T")])
        assert config.incremental_mode == "new_only"
        assert config.state_path == "/tmp/state.json"
        assert config.archive_dir == "/tmp/archive"
        assert config.archive_granularity == "week"
        assert config.asset_db_path == "/tmp/assets.db"
        assert config.observability_jsonl_path == "/tmp/observability.jsonl"
        assert config.observability_exporter == "jsonl"
        assert config.otlp_endpoint == "http://127.0.0.1:4318/v1/traces"
        assert config.orchestration_mode == "prefect"
        assert config.prefect_deployment_name == "demo/tech-blog"
        assert config.delivery_webhook_url == "https://example.com/webhook"
        assert config.delivery_roles == ["executive", "engineer"]
        assert config.delivery_cadence == "weekly"
        assert config.delivery_rate_limit_per_minute == 5
        assert config.delivery_max_retries == 4
        assert config.stack_profile_path == "/tmp/stack_profile.yaml"
        assert config.stack_repo_roots == ["/repo/a", "/repo/b"]
        assert config.fetch_content is False
        assert config.content_timeout == 20

    def test_invalid_orchestration_mode_is_reported(self):
        config = TechBlogMonitorConfig(
            feeds=[FeedSource("D", "https://d.com/rss", "T")],
            orchestration_mode="broken",
        )
        errors = config.validate()
        assert any("orchestration_mode" in error for error in errors)

    def test_invalid_int_env_does_not_raise(self, monkeypatch):
        """非法整数环境变量不抛异常，使用默认值并记录解析错误。"""
        monkeypatch.setenv("TECH_BLOG_FETCH_WORKERS", "abc")
        config = TechBlogMonitorConfig(feeds=[FeedSource("D", "https://d.com/rss", "T")])
        assert config.fetch_workers == 5  # 默认值
        assert any("TECH_BLOG_FETCH_WORKERS" in e for e in config._parse_errors)

    def test_invalid_int_appears_in_validate(self, monkeypatch):
        monkeypatch.setenv("TECH_BLOG_FETCH_WORKERS", "abc")
        config = TechBlogMonitorConfig(feeds=[FeedSource("D", "https://d.com/rss", "T")])
        errors = config.validate()
        assert any("TECH_BLOG_FETCH_WORKERS" in e for e in errors)

    def test_bad_yaml_appears_in_validate(self, tmp_path, monkeypatch):
        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text("not_feeds: true\n")
        monkeypatch.setenv("TECH_BLOG_FEEDS_YAML", str(bad_yaml))
        config = TechBlogMonitorConfig()
        errors = config.validate()
        assert any("feeds" in e for e in errors)

    def test_missing_yaml_file_appears_in_validate(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TECH_BLOG_FEEDS_YAML", str(tmp_path / "missing.yaml"))
        config = TechBlogMonitorConfig()
        errors = config.validate()
        assert any("不存在" in e for e in errors)

    def test_jsonl_exporter_requires_jsonl_path(self):
        config = TechBlogMonitorConfig(
            feeds=[FeedSource("D", "https://d.com/rss", "T")],
            observability_exporter="jsonl",
            observability_jsonl_path="",
        )
        errors = config.validate()
        assert any("observability_jsonl_path" in error for error in errors)

    def test_invalid_observability_exporter_appears_in_validate(self):
        config = TechBlogMonitorConfig(
            feeds=[FeedSource("D", "https://d.com/rss", "T")],
            observability_exporter="bad_exporter",
        )
        errors = config.validate()
        assert any("observability_exporter" in error for error in errors)


# ── validate() 值域校验 ───────────────────────────────────────────────────────

class TestValidate:
    def _base(self):
        return TechBlogMonitorConfig(feeds=[FeedSource("D", "https://d.com/rss", "T")])

    def test_valid_config_no_errors(self):
        assert self._base().validate() == []

    def test_invalid_fetch_workers_zero(self, monkeypatch):
        monkeypatch.setenv("TECH_BLOG_FETCH_WORKERS", "0")
        config = TechBlogMonitorConfig(feeds=[FeedSource("D", "https://d.com/rss", "T")])
        errors = config.validate()
        assert any("fetch_workers" in e for e in errors)

    def test_invalid_content_workers_zero(self, monkeypatch):
        monkeypatch.setenv("TECH_BLOG_CONTENT_WORKERS", "0")
        config = TechBlogMonitorConfig(feeds=[FeedSource("D", "https://d.com/rss", "T")])
        errors = config.validate()
        assert any("content_workers" in e for e in errors)

    def test_invalid_view(self, monkeypatch):
        monkeypatch.setenv("TECH_BLOG_VIEW", "by_magic")
        config = TechBlogMonitorConfig(feeds=[FeedSource("D", "https://d.com/rss", "T")])
        errors = config.validate()
        assert any("view" in e for e in errors)

    def test_invalid_incremental_mode(self, monkeypatch):
        monkeypatch.setenv("TECH_BLOG_INCREMENTAL_MODE", "magic")
        config = TechBlogMonitorConfig(feeds=[FeedSource("D", "https://d.com/rss", "T")])
        errors = config.validate()
        assert any("incremental_mode" in e for e in errors)

    def test_invalid_delivery_role(self, monkeypatch):
        monkeypatch.setenv("TECH_BLOG_DELIVERY_ROLES", "executive,unknown")
        monkeypatch.setenv("TECH_BLOG_DELIVERY_WEBHOOK", "https://example.com/webhook")
        monkeypatch.setenv("TECH_BLOG_ASSET_DB_PATH", "/tmp/assets.db")
        config = TechBlogMonitorConfig(feeds=[FeedSource("D", "https://d.com/rss", "T")])
        errors = config.validate()
        assert any("delivery_roles" in e for e in errors)

    def test_delivery_requires_asset_db_and_webhook(self, monkeypatch):
        monkeypatch.setenv("TECH_BLOG_DELIVERY_ROLES", "executive")
        config = TechBlogMonitorConfig(feeds=[FeedSource("D", "https://d.com/rss", "T")])
        errors = config.validate()
        assert any("delivery_webhook_url" in e for e in errors)

    def test_new_only_requires_state_path(self):
        config = TechBlogMonitorConfig(
            feeds=[FeedSource("D", "https://d.com/rss", "T")],
            incremental_mode="new_only",
        )
        errors = config.validate()
        assert any("state_path" in e for e in errors)

    def test_invalid_archive_granularity(self):
        config = TechBlogMonitorConfig(
            feeds=[FeedSource("D", "https://d.com/rss", "T")],
            archive_granularity="month",
        )
        errors = config.validate()
        assert any("archive_granularity" in e for e in errors)

    def test_empty_feeds(self):
        config = TechBlogMonitorConfig(feeds=[])
        errors = config.validate()
        assert any("feeds" in e for e in errors)

    def test_negative_max_age_days(self, monkeypatch):
        monkeypatch.setenv("TECH_BLOG_MAX_AGE_DAYS", "-1")
        config = TechBlogMonitorConfig(feeds=[FeedSource("D", "https://d.com/rss", "T")])
        errors = config.validate()
        assert any("max_age_days" in e for e in errors)

    def test_error_messages_contain_field_and_value(self, monkeypatch):
        monkeypatch.setenv("TECH_BLOG_VIEW", "bad_view")
        config = TechBlogMonitorConfig(feeds=[FeedSource("D", "https://d.com/rss", "T")])
        errors = config.validate()
        assert any("bad_view" in e for e in errors)
