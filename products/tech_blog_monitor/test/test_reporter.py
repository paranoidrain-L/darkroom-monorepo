# -*- coding: utf-8 -*-
"""Tech Blog Monitor reporter 单元测试。"""

from datetime import datetime, timezone

from products.tech_blog_monitor.fetcher import Article, FeedHealth
from products.tech_blog_monitor.reporter import _clean_ai_summary, _clean_trend_md, build_report


def _article(title="T", url="https://example.com/1", published=None, rss_summary="raw",
             category="行业风向标", source="S", ai_summary=""):
    return Article(
        title=title, url=url, published=published, rss_summary=rss_summary,
        source_name=source, category=category, ai_summary=ai_summary,
        source_id=f"{source}::{url}",
        published_ts=int(published.timestamp()) if published else None,
        fetched_at=0,
    )


_PUB = datetime(2026, 4, 10, tzinfo=timezone.utc)


# ── _clean_trend_md ───────────────────────────────────────────────────────────

class TestCleanTrendMd:
    def test_removes_duplicate_heading(self):
        md = "## 技术趋势分析\n\n热点：LLM"
        assert "技术趋势分析" not in _clean_trend_md(md)
        assert "热点：LLM" in _clean_trend_md(md)

    def test_removes_h1_heading(self):
        md = "# 趋势分析\n内容"
        assert "趋势分析" not in _clean_trend_md(md)

    def test_removes_variant_with_suffix(self):
        """# 技术趋势分析报告 这类带后缀的变体也应被清除。"""
        md = "# 技术趋势分析报告\n\n内容"
        result = _clean_trend_md(md)
        assert "技术趋势分析报告" not in result
        assert "内容" in result

    def test_removes_trend_analysis_english(self):
        md = "## Trend Analysis Report\n内容"
        assert "Trend Analysis" not in _clean_trend_md(md)

    def test_no_heading_unchanged(self):
        md = "热点：LLM\n- 智能体"
        assert _clean_trend_md(md) == md

    def test_strips_surrounding_whitespace(self):
        md = "\n\n## 技术趋势分析\n\n内容\n\n"
        result = _clean_trend_md(md)
        assert not result.startswith("\n")
        assert not result.endswith("\n")


# ── _clean_ai_summary ─────────────────────────────────────────────────────────

class TestCleanAiSummary:
    def test_removes_blockquote_prefix(self):
        assert _clean_ai_summary("> 这是摘要") == "这是摘要"

    def test_removes_trailing_blank_lines(self):
        result = _clean_ai_summary("摘要内容\n\n\n")
        assert not result.endswith("\n")

    def test_multiline_joined(self):
        result = _clean_ai_summary("> 第一句\n> 第二句")
        assert "第一句" in result
        assert "第二句" in result

    def test_plain_text_unchanged(self):
        assert _clean_ai_summary("普通摘要") == "普通摘要"


# ── build_report 基础 ─────────────────────────────────────────────────────────

def test_build_report_renders_trend_and_articles():
    articles = [
        _article(title="Article A", url="https://example.com/a", published=_PUB,
                 category="行业风向标", ai_summary="AI 摘要 A"),
        _article(title="Article B", url="https://example.com/b",
                 category="深度技术", rss_summary="raw summary B"),
    ]
    report = build_report(articles, "## 热点主题\n- 智能体\n")

    assert "# 技术博客阅读报告" in report
    assert "## 技术趋势分析" in report
    assert "### 行业风向标（1 篇）" in report
    assert "### 深度技术（1 篇）" in report
    assert "> AI 摘要 A" in report
    assert "> raw summary B" in report


def test_build_report_deduplicates_trend_heading():
    """trend_md 自带标题时，报告中不出现两个"技术趋势分析"。"""
    articles = [_article()]
    report = build_report(articles, "## 技术趋势分析\n热点内容")
    assert report.count("技术趋势分析") == 1


def test_build_report_renders_health_summary():
    articles = [_article(url="https://example.com/a", published=_PUB)]
    health_list = [
        FeedHealth(name="Source A", url="https://a.rss", success=True, article_count=1, retries=1),
        FeedHealth(name="Source B", url="https://b.rss", success=False, error="404"),
    ]
    report = build_report(articles, "", health_list)

    assert "## Feed 抓取状态" in report
    assert "成功 1 个 / 失败 1 个 / 共 2 个" in report
    assert "Source B" in report
    assert "404" in report
    assert "重试1次" in report


# ── 双视图 ────────────────────────────────────────────────────────────────────

def test_build_report_by_category_groups_by_category():
    articles = [
        _article(title="A", url="https://x.com/1", category="行业风向标"),
        _article(title="B", url="https://x.com/2", category="深度技术"),
    ]
    report = build_report(articles, "", view="by_category")
    assert "### 行业风向标" in report
    assert "### 深度技术" in report


def test_build_report_by_time_no_category_headers():
    articles = [
        _article(title="A", url="https://x.com/1", category="行业风向标",
                 published=datetime(2026, 4, 10, tzinfo=timezone.utc)),
        _article(title="B", url="https://x.com/2", category="深度技术",
                 published=datetime(2026, 4, 9, tzinfo=timezone.utc)),
    ]
    report = build_report(articles, "", view="by_time")
    assert "### 行业风向标" not in report
    assert "### 深度技术" not in report
    # 较新的文章在前
    assert report.index("Article A") < report.index("Article B") if "Article A" in report else True


def test_build_report_by_time_order():
    newer = _article(title="Newer", url="https://x.com/1",
                     published=datetime(2026, 4, 13, tzinfo=timezone.utc))
    older = _article(title="Older", url="https://x.com/2",
                     published=datetime(2026, 4, 10, tzinfo=timezone.utc))
    report = build_report([older, newer], "", view="by_time")
    assert report.index("Newer") < report.index("Older")


# ── 增量视图 ──────────────────────────────────────────────────────────────────

def test_build_report_new_urls_shows_two_sections():
    new_url = "https://x.com/new"
    old_url = "https://x.com/old"
    articles = [
        _article(title="New Article", url=new_url, published=_PUB),
        _article(title="Old Article", url=old_url, published=_PUB),
    ]
    report = build_report(articles, "", new_urls={new_url})

    assert "## 本次新增" in report
    assert "## 全部文章" in report
    assert "🆕" in report


def test_build_report_new_urls_badge_only_on_new():
    new_url = "https://x.com/new"
    old_url = "https://x.com/old"
    articles = [
        _article(title="New", url=new_url, published=_PUB),
        _article(title="Old", url=old_url, published=_PUB),
    ]
    report = build_report(articles, "", new_urls={new_url})
    # 🆕 只出现在新文章行
    lines_with_badge = [line for line in report.splitlines() if "🆕" in line]
    assert all("New" in line for line in lines_with_badge)


def test_build_report_all_new_no_split():
    """所有文章都是新的时，不拆分两个视图。"""
    urls = {"https://x.com/1", "https://x.com/2"}
    articles = [_article(url=u, published=_PUB) for u in urls]
    report = build_report(articles, "", new_urls=urls)
    assert "## 本次新增" not in report
    assert "## 全部文章" not in report


def test_build_report_no_new_urls_no_split():
    articles = [_article(published=_PUB)]
    report = build_report(articles, "")
    assert "## 本次新增" not in report
    assert "## 全部文章" not in report
    assert "## 文章列表" in report


def test_build_report_new_only_mode_only_renders_new_section():
    new_url = "https://x.com/new"
    articles = [_article(title="New", url=new_url, published=_PUB)]
    report = build_report(articles, "", new_urls={new_url}, incremental_mode="new_only")
    assert "## 本次新增（1 篇）" in report
    assert "## 全部文章" not in report


def test_build_report_new_only_mode_handles_no_new_articles():
    report = build_report([], "", new_urls=set(), incremental_mode="new_only")
    assert "## 本次新增（0 篇）" in report
    assert "本次无新增文章。" in report
