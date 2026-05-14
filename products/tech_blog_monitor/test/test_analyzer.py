# -*- coding: utf-8 -*-
"""Tech Blog Monitor analyzer 单元测试。"""

import threading
import time
from datetime import datetime, timezone

from products.tech_blog_monitor.analyzer import (
    _TREND_FALLBACK,
    _enrichment_batches,
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
            '[{"index": 0, "one_line_summary": "一句话", "detailed_summary": "更详细的摘要。", "key_points": ["点1"], '
            '"why_it_matters": "很重要", "recommended_for": ["工程师"], '
            '"tags": ["agent"], "topic": "智能体"}]'
        )
        result, item_errors, err = _parse_enrichments(raw, 1)
        assert err is None
        assert item_errors == {}
        assert result[0].one_line_summary == "一句话"
        assert result[0].detailed_summary == "更详细的摘要。"

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
            "好的，结果如下\n"
            '[{"index": 0, "one_line_summary": "一句话", "detailed_summary": "更详细的摘要。", "key_points": ["点1"], '
            '"why_it_matters": "很重要", "recommended_for": ["工程师"], '
            '"tags": ["agent"], "topic": "智能体"}]\n'
            "结束"
        )
        result, item_errors, err = _parse_enrichments(raw, 1)
        assert err is None
        assert item_errors == {}
        assert result[0].topic == "智能体"


class TestAnalyze:
    def test_enrichment_batches_split_articles(self):
        batches = _enrichment_batches([_article("a"), _article("b"), _article("c")], batch_size=2)
        assert len(batches) == 2
        assert [article.title for article in batches[0]] == ["a", "b"]
        assert [article.title for article in batches[1]] == ["c"]

    def test_fills_structured_enrichment_and_trend(self, monkeypatch):
        client = _FakeClient(
            [
                (
                    '[{"index": 0, "one_line_summary": "中文摘要A", "detailed_summary": "中文详细摘要A", "key_points": ["点A", "限制点评：接入前需要校验兼容性"], '
                    '"why_it_matters": "原因A", "recommended_for": ["工程师"], '
                    '"tags": ["agent"], "topic": "智能体"}, '
                    '{"index": 1, "one_line_summary": "中文摘要B", "detailed_summary": "中文详细摘要B", "key_points": ["点B", "限制点评：仍依赖特定部署前提"], '
                    '"why_it_matters": "原因B", "recommended_for": ["研究员"], '
                    '"tags": ["infra"], "topic": "基础设施"}]'
                ),
                "## 本期热点主题\n- 智能体工程\n",
            ]
        )
        monkeypatch.setattr("products.tech_blog_monitor.analyzer._get_client", lambda backend: client)

        articles, trend_md = analyze([_article("a"), _article("b")], backend="codex")

        assert articles[0].ai_summary == "中文详细摘要A"
        assert articles[0].one_line_summary == "中文摘要A"
        assert articles[0].key_points == ["点A", "限制点评：接入前需要校验兼容性"]
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
        client = _FakeClient(
            [
                (
                    '[{"index": 0, "one_line_summary": "中文摘要A", "detailed_summary": "中文详细摘要A", "key_points": ["点A", "限制点评：需要额外压测"], '
                    '"why_it_matters": "原因A", "recommended_for": ["工程师"], '
                    '"tags": ["agent"], "topic": "智能体"}, '
                    '{"index": 1, "one_line_summary": "坏条目", "key_points": "bad", '
                    '"why_it_matters": "原因B", "recommended_for": ["研究员"], '
                    '"tags": ["infra"], "topic": "基础设施"}]'
                ),
                "## 本期热点主题\n- 智能体工程\n",
            ]
        )
        monkeypatch.setattr("products.tech_blog_monitor.analyzer._get_client", lambda backend: client)

        articles, _ = analyze([_article("a"), _article("b")], backend="trae")

        assert articles[0].enrichment_status == "enriched"
        assert articles[1].enrichment_status == "failed"
        assert articles[1].one_line_summary == ""
        assert articles[1].enrichment_error

    def test_invalid_json_does_not_crash(self, monkeypatch):
        client = _FakeClient(
            [
                "这不是 JSON",
                "## 热点\n内容",
            ]
        )
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
        client = _FakeClient(
            [
                (
                    '[{"index": 0, "one_line_summary": "摘要", "detailed_summary": "详细摘要", "key_points": ["点A", "限制点评：需要额外验证"], '
                    '"why_it_matters": "原因", "recommended_for": ["工程师"], '
                    '"tags": ["agent"], "topic": "智能体"}]'
                ),
                "趋势内容",
            ]
        )

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
        assert "detailed_summary" in enrichment_prompt
        assert "技术机制" in enrichment_prompt
        assert "关键变化" in enrichment_prompt
        assert "限制点评：" in enrichment_prompt
        assert "不要只写“值得关注”" in enrichment_prompt

    def test_enrichment_prompt_can_include_full_clean_text(self, monkeypatch):
        long_text = "开头内容 " + ("中间内容 " * 200) + "完整正文结尾标记"
        captured = {}
        client = _FakeClient(
            [
                (
                    '[{"index": 0, "one_line_summary": "摘要", "detailed_summary": "详细摘要", "key_points": ["点A", "限制点评：需要额外验证"], '
                    '"why_it_matters": "原因", "recommended_for": ["工程师"], '
                    '"tags": ["agent"], "topic": "智能体"}]'
                ),
                "趋势内容",
            ]
        )

        original_chat = client.chat

        def capturing_chat(prompt):
            captured["prompts"] = captured.get("prompts", []) + [prompt]
            return original_chat(prompt)

        client.chat = capturing_chat
        monkeypatch.setattr("products.tech_blog_monitor.analyzer._get_client", lambda backend: client)
        monkeypatch.setenv("TECH_BLOG_ENRICHMENT_CONTENT_CHARS", "0")

        analyze([_article("x", clean_text=long_text)], backend="trae")

        enrichment_prompt = captured["prompts"][0]
        assert "正文内容:" in enrichment_prompt
        assert "开头内容" in enrichment_prompt
        assert "完整正文结尾标记" in enrichment_prompt

    def test_enrichment_prompt_respects_content_char_limit(self, monkeypatch):
        long_text = "abcdefghijklmnopqrstuvwxyz"
        captured = {}
        client = _FakeClient(
            [
                (
                    '[{"index": 0, "one_line_summary": "摘要", "detailed_summary": "详细摘要", "key_points": ["点A", "限制点评：需要额外验证"], '
                    '"why_it_matters": "原因", "recommended_for": ["工程师"], '
                    '"tags": ["agent"], "topic": "智能体"}]'
                ),
                "趋势内容",
            ]
        )

        original_chat = client.chat

        def capturing_chat(prompt):
            captured["prompts"] = captured.get("prompts", []) + [prompt]
            return original_chat(prompt)

        client.chat = capturing_chat
        monkeypatch.setattr("products.tech_blog_monitor.analyzer._get_client", lambda backend: client)
        monkeypatch.setenv("TECH_BLOG_ENRICHMENT_CONTENT_CHARS", "10")

        analyze([_article("x", clean_text=long_text)], backend="trae")

        enrichment_prompt = captured["prompts"][0]
        assert "abcdefghij" in enrichment_prompt
        assert "klmnopqrstuvwxyz" not in enrichment_prompt

    def test_missing_detailed_summary_falls_back_to_one_line_summary(self, monkeypatch):
        client = _FakeClient(
            [
                (
                    '[{"index": 0, "one_line_summary": "中文摘要A", "key_points": ["点A", "限制点评：上下文仍然不足"], '
                    '"why_it_matters": "原因A", "recommended_for": ["工程师"], '
                    '"tags": ["agent"], "topic": "智能体"}]'
                ),
                "## 本期热点主题\n- 智能体工程\n",
            ]
        )
        monkeypatch.setattr("products.tech_blog_monitor.analyzer._get_client", lambda backend: client)

        articles, _ = analyze([_article("a")], backend="codex")

        assert articles[0].one_line_summary == "中文摘要A"
        assert articles[0].ai_summary == "中文摘要A"

    def test_analyze_enriches_in_multiple_batches(self, monkeypatch):
        client = _FakeClient(
            [
                (
                    '[{"index": 0, "one_line_summary": "摘要1", "detailed_summary": "详细1", "key_points": ["点1", "限制点评：前提1"], '
                    '"why_it_matters": "原因1", "recommended_for": ["工程师"], "tags": ["a"], "topic": "主题1"}, '
                    '{"index": 1, "one_line_summary": "摘要2", "detailed_summary": "详细2", "key_points": ["点2", "限制点评：前提2"], '
                    '"why_it_matters": "原因2", "recommended_for": ["工程师"], "tags": ["b"], "topic": "主题2"}]'
                ),
                (
                    '[{"index": 0, "one_line_summary": "摘要3", "detailed_summary": "详细3", "key_points": ["点3", "限制点评：前提3"], '
                    '"why_it_matters": "原因3", "recommended_for": ["研究员"], "tags": ["c"], "topic": "主题3"}]'
                ),
                "## 本期热点主题\n- 批处理\n",
            ]
        )
        monkeypatch.setattr("products.tech_blog_monitor.analyzer._get_client", lambda backend: client)
        monkeypatch.setattr("products.tech_blog_monitor.analyzer._ENRICHMENT_BATCH_SIZE", 2)

        articles, trend_md = analyze([_article("a"), _article("b"), _article("c")], backend="codex")

        assert [article.one_line_summary for article in articles] == ["摘要1", "摘要2", "摘要3"]
        assert all(article.enrichment_status == "enriched" for article in articles)
        assert "批处理" in trend_md
        assert len(client.prompts) == 3

    def test_analyze_can_enrich_batches_in_parallel(self, monkeypatch):
        class _ConcurrentFakeClient:
            def __init__(self) -> None:
                self.lock = threading.Lock()
                self.active = 0
                self.max_active = 0
                self.prompts: list[str] = []

            def chat(self, prompt: str) -> str:
                with self.lock:
                    self.prompts.append(prompt)
                    self.active += 1
                    self.max_active = max(self.max_active, self.active)
                try:
                    if "文章标题列表：" not in prompt:
                        time.sleep(0.05)
                    if "标题: a" in prompt:
                        return (
                            '[{"index": 0, "one_line_summary": "摘要A", "detailed_summary": "详细A", '
                            '"key_points": ["点A", "限制点评：前提A"], "why_it_matters": "原因A", '
                            '"recommended_for": ["工程师"], "tags": ["a"], "topic": "主题A"}]'
                        )
                    if "标题: b" in prompt:
                        return (
                            '[{"index": 0, "one_line_summary": "摘要B", "detailed_summary": "详细B", '
                            '"key_points": ["点B", "限制点评：前提B"], "why_it_matters": "原因B", '
                            '"recommended_for": ["工程师"], "tags": ["b"], "topic": "主题B"}]'
                        )
                    return "## 本期热点主题\n- 并发处理\n"
                finally:
                    with self.lock:
                        self.active -= 1

        client = _ConcurrentFakeClient()
        monkeypatch.setattr("products.tech_blog_monitor.analyzer._get_client", lambda backend: client)
        monkeypatch.setattr("products.tech_blog_monitor.analyzer._ENRICHMENT_BATCH_SIZE", 1)
        monkeypatch.setenv("TECH_BLOG_ENRICHMENT_WORKERS", "2")

        articles, trend_md = analyze([_article("a"), _article("b")], backend="codex")

        assert [article.one_line_summary for article in articles] == ["摘要A", "摘要B"]
        assert all(article.enrichment_status == "enriched" for article in articles)
        assert "并发处理" in trend_md
        assert client.max_active == 2
        assert len(client.prompts) == 3
