# -*- coding: utf-8 -*-
"""Tech Blog Monitor analyzer 单元测试。"""

from datetime import datetime, timezone

from products.tech_blog_monitor.analyzer import (
    _TREND_FALLBACK,
    _parse_enrichments,
    analyze,
    check_backend,
)
from products.tech_blog_monitor.fetcher import Article


class _FakeClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.prompts: list[str] = []

    def chat(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self._responses[len(self.prompts) - 1]


def _article(title: str, clean_text: str = "") -> Article:
    return Article(
        title=title,
        url=f"https://example.com/{title}",
        source_name="Example Feed",
        category="测试分类",
        source_id=f"Example Feed::https://example.com/{title}",
        rss_summary=f"{title} raw summary",
        clean_text=clean_text,
        content_status="fetched" if clean_text else "not_fetched",
        published=datetime(2026, 4, 10, tzinfo=timezone.utc),
        published_ts=1744243200,
        fetched_at=1744243200,
    )


class TestCheckBackend:
    def test_known_backends_return_none(self):
        for backend in ("claude", "claude_code", "trae", "codex"):
            assert check_backend(backend) is None

    def test_unknown_backend_returns_error(self):
        err = check_backend("magic_ai")
        assert err is not None
        assert "magic_ai" in err

    def test_empty_string_returns_error(self):
        assert check_backend("") is not None


class TestParseEnrichments:
    def test_valid_json(self):
        raw = (
            '[{"index": 0, "one_line_summary": "一句话", "key_points": ["点1"], '
            '"why_it_matters": "很重要", "recommended_for": ["工程师"], '
            '"tags": ["agent"], "topic": "智能体"}]'
        )
        result, item_errors, err = _parse_enrichments(raw, 1)
        assert err is None
        assert item_errors == {}
        assert result[0].one_line_summary == "一句话"

    def test_invalid_json_returns_fatal_error(self):
        result, item_errors, err = _parse_enrichments("[{broken", 1)
        assert result == {}
        assert item_errors == {}
        assert err is not None

    def test_invalid_item_isolated_into_item_errors(self):
        raw = (
            '[{"index": 0, "one_line_summary": "一句话", "key_points": "bad", '
            '"why_it_matters": "很重要", "recommended_for": ["工程师"], '
            '"tags": ["agent"], "topic": "智能体"}]'
        )
        result, item_errors, err = _parse_enrichments(raw, 1)
        assert result == {}
        assert 0 in item_errors
        assert err is not None

    def test_json_embedded_in_text_still_parses(self):
        raw = (
            '好的，结果如下\n'
            '[{"index": 0, "one_line_summary": "一句话", "key_points": ["点1"], '
            '"why_it_matters": "很重要", "recommended_for": ["工程师"], '
            '"tags": ["agent"], "topic": "智能体"}]\n'
            '结束'
        )
        result, item_errors, err = _parse_enrichments(raw, 1)
        assert err is None
        assert item_errors == {}
        assert result[0].topic == "智能体"


class TestAnalyze:
    def test_fills_structured_enrichment_and_trend(self, monkeypatch):
        client = _FakeClient([
            (
                '[{"index": 0, "one_line_summary": "中文摘要A", "key_points": ["点A"], '
                '"why_it_matters": "原因A", "recommended_for": ["工程师"], '
                '"tags": ["agent"], "topic": "智能体"}, '
                '{"index": 1, "one_line_summary": "中文摘要B", "key_points": ["点B"], '
                '"why_it_matters": "原因B", "recommended_for": ["研究员"], '
                '"tags": ["infra"], "topic": "基础设施"}]'
            ),
            "## 本期热点主题\n- 智能体工程\n",
        ])
        monkeypatch.setattr("products.tech_blog_monitor.analyzer._get_client", lambda backend: client)

        articles, trend_md = analyze([_article("a"), _article("b")], backend="codex")

        assert articles[0].ai_summary == "中文摘要A"
        assert articles[0].one_line_summary == "中文摘要A"
        assert articles[0].key_points == ["点A"]
        assert articles[0].why_it_matters == "原因A"
        assert articles[0].recommended_for == ["工程师"]
        assert articles[0].tags == ["agent"]
        assert articles[0].topic == "智能体"
        assert articles[0].enrichment_status == "enriched"
        assert articles[1].topic == "基础设施"
        assert "热点主题" in trend_md
        assert len(client.prompts) == 2

    def test_unknown_backend_returns_fallback_and_marks_failed(self, monkeypatch):
        called = {"n": 0}
        monkeypatch.setattr(
            "products.tech_blog_monitor.analyzer._get_client",
            lambda backend: called.update({"n": called["n"] + 1}),
        )

        articles, trend_md = analyze([_article("x")], backend="unknown_backend")

        assert called["n"] == 0
        assert trend_md == _TREND_FALLBACK
        assert articles[0].enrichment_status == "failed"
        assert articles[0].one_line_summary == ""

    def test_client_failure_marks_all_failed_and_returns_fallback_trend(self, monkeypatch):
        class _FailingClient:
            def chat(self, prompt: str) -> str:
                raise RuntimeError("network error")

        monkeypatch.setattr("products.tech_blog_monitor.analyzer._get_client", lambda backend: _FailingClient())

        articles, trend_md = analyze([_article("x")], backend="claude")

        assert trend_md == _TREND_FALLBACK
        assert articles[0].enrichment_status == "failed"
        assert "network error" in articles[0].enrichment_error

    def test_client_init_failure_returns_fallback_and_marks_failed(self, monkeypatch):
        monkeypatch.setattr(
            "products.tech_blog_monitor.analyzer._get_client",
            lambda backend: (_ for _ in ()).throw(RuntimeError("init failed")),
        )

        articles, trend_md = analyze([_article("x")], backend="claude")

        assert trend_md == _TREND_FALLBACK
        assert articles[0].enrichment_status == "failed"
        assert "init failed" in articles[0].enrichment_error
        assert articles[0].one_line_summary == ""

    def test_partial_success_isolated_per_article(self, monkeypatch):
        client = _FakeClient([
            (
                '[{"index": 0, "one_line_summary": "中文摘要A", "key_points": ["点A"], '
                '"why_it_matters": "原因A", "recommended_for": ["工程师"], '
                '"tags": ["agent"], "topic": "智能体"}, '
                '{"index": 1, "one_line_summary": "坏条目", "key_points": "bad", '
                '"why_it_matters": "原因B", "recommended_for": ["研究员"], '
                '"tags": ["infra"], "topic": "基础设施"}]'
            ),
            "## 本期热点主题\n- 智能体工程\n",
        ])
        monkeypatch.setattr("products.tech_blog_monitor.analyzer._get_client", lambda backend: client)

        articles, _ = analyze([_article("a"), _article("b")], backend="trae")

        assert articles[0].enrichment_status == "enriched"
        assert articles[1].enrichment_status == "failed"
        assert articles[1].one_line_summary == ""
        assert articles[1].enrichment_error

    def test_invalid_json_does_not_crash(self, monkeypatch):
        client = _FakeClient([
            "这不是 JSON",
            "## 热点\n内容",
        ])
        monkeypatch.setattr("products.tech_blog_monitor.analyzer._get_client", lambda backend: client)

        articles, trend_md = analyze([_article("x")], backend="trae")

        assert articles[0].enrichment_status == "failed"
        assert articles[0].one_line_summary == ""
        assert "热点" in trend_md

    def test_empty_articles_returns_early(self, monkeypatch):
        called = {"n": 0}
        monkeypatch.setattr(
            "products.tech_blog_monitor.analyzer._get_client",
            lambda backend: called.update({"n": 1}),
        )

        articles, trend_md = analyze([], backend="trae")

        assert articles == []
        assert trend_md == ""
        assert called["n"] == 0

    def test_enrichment_prompt_prefers_clean_text(self, monkeypatch):
        captured = {}
        client = _FakeClient([
            (
                '[{"index": 0, "one_line_summary": "摘要", "key_points": ["点A"], '
                '"why_it_matters": "原因", "recommended_for": ["工程师"], '
                '"tags": ["agent"], "topic": "智能体"}]'
            ),
            "趋势内容",
        ])

        original_chat = client.chat

        def capturing_chat(prompt):
            captured["prompts"] = captured.get("prompts", []) + [prompt]
            return original_chat(prompt)

        client.chat = capturing_chat
        monkeypatch.setattr("products.tech_blog_monitor.analyzer._get_client", lambda backend: client)
        analyze([_article("x", clean_text="clean text body")], backend="trae")

        enrichment_prompt = captured["prompts"][0]
        assert "clean text body" in enrichment_prompt
        assert "one_line_summary" in enrichment_prompt
