# -*- coding: utf-8 -*-
"""Tech Blog Monitor content_fetcher 单元测试。"""

from pathlib import Path
from types import SimpleNamespace

from products.tech_blog_monitor.content_fetcher import (
    extract_clean_text,
    fetch_article_content,
    fetch_contents,
)
from products.tech_blog_monitor.extractors import ExtractionResult
from products.tech_blog_monitor.fetcher import Article


def _fixture(name: str) -> str:
    base = Path(__file__).parent / "fixtures"
    return (base / name).read_text(encoding="utf-8")


def _article(url="https://example.com/a") -> Article:
    return Article(
        title="Article A",
        url=url,
        source_name="Source A",
        category="行业风向标",
        source_id=f"Source A::{url}",
        rss_summary="raw summary",
        published=None,
        published_ts=None,
        fetched_at=1744243200,
    )


def _response(text: str, status_code: int = 200, url: str = "https://example.com/final"):
    return SimpleNamespace(text=text, status_code=status_code, url=url)


def test_extract_clean_text_from_article_fixture():
    text, source = extract_clean_text(_fixture("article_page.html"), max_chars=500)
    assert "This is the first paragraph." in text
    assert "This is the second paragraph." in text
    assert source == "html_article"


def test_extract_clean_text_from_json_ld_fixture():
    text, source = extract_clean_text(_fixture("json_ld_page.html"), max_chars=500)
    assert "structured data" in text
    assert source == "json_ld"


def test_extract_clean_text_returns_empty_for_no_content_fixture():
    text, source = extract_clean_text(_fixture("no_content_page.html"), max_chars=500)
    assert text == ""
    assert source == ""


def test_extract_clean_text_respects_max_chars():
    text, source = extract_clean_text(_fixture("long_page.html"), max_chars=60)
    assert source == "html_main"
    assert len(text) <= 60


def test_fetch_article_content_marks_http_error():
    article = _article()
    result = fetch_article_content(
        article,
        requester=SimpleNamespace(get=lambda *args, **kwargs: _response("forbidden", status_code=403)),
    )
    assert result.content_status == "http_error"
    assert result.content_http_status == 403


def test_fetch_article_content_marks_fetch_error():
    article = _article()

    def failing_get(*args, **kwargs):
        raise RuntimeError("network down")

    result = fetch_article_content(article, requester=SimpleNamespace(get=failing_get))
    assert result.content_status == "fetch_error"
    assert "network down" in result.content_error


def test_fetch_article_content_fills_clean_text():
    article = _article()
    result = fetch_article_content(
        article,
        requester=SimpleNamespace(get=lambda *args, **kwargs: _response(_fixture("article_page.html"))),
        content_extractor="heuristic",
    )
    assert result.content_status == "fetched"
    assert result.clean_text
    assert result.content_source == "html_article"
    assert result.content_final_url == "https://example.com/final"


def test_fetch_article_content_prefers_trafilatura(monkeypatch):
    article = _article()
    import products.tech_blog_monitor.content_fetcher as module

    monkeypatch.setattr(
        module,
        "trafilatura_extract_content",
        lambda html_text, *, url="", max_chars=20000: ExtractionResult(
            clean_text="Trafilatura extracted body.\n\nSecond paragraph with enough detail.",
            source="trafilatura",
        ),
    )
    monkeypatch.setattr(
        module,
        "heuristic_extract_content",
        lambda html_text, *, url="", max_chars=20000: ExtractionResult(
            clean_text="Heuristic fallback body that should not be used.",
            source="html_article",
        ),
    )

    result = fetch_article_content(
        article,
        requester=SimpleNamespace(get=lambda *args, **kwargs: _response(_fixture("article_page.html"))),
    )

    assert result.content_status == "fetched"
    assert result.clean_text.startswith("Trafilatura extracted body.")
    assert result.content_source == "trafilatura"


def test_fetch_article_content_uses_heuristic_when_trafilatura_returns_empty(monkeypatch):
    article = _article()
    import products.tech_blog_monitor.content_fetcher as module

    monkeypatch.setattr(
        module,
        "trafilatura_extract_content",
        lambda html_text, *, url="", max_chars=20000: ExtractionResult(
            clean_text="",
            source="trafilatura",
            error="trafilatura_empty",
        ),
    )

    result = fetch_article_content(
        article,
        requester=SimpleNamespace(get=lambda *args, **kwargs: _response(_fixture("article_page.html"))),
        playwright_fallback=False,
    )

    assert result.content_status == "fetched"
    assert result.clean_text
    assert result.content_source == "html_article"


def test_fetch_article_content_marks_low_quality(monkeypatch):
    article = _article()
    import products.tech_blog_monitor.content_fetcher as module

    monkeypatch.setattr(
        module,
        "trafilatura_extract_content",
        lambda html_text, *, url="", max_chars=20000: ExtractionResult(
            clean_text="Menu\nLogin\nPrivacy\nCookie",
            source="trafilatura",
        ),
    )
    monkeypatch.setattr(
        module,
        "heuristic_extract_content",
        lambda html_text, *, url="", max_chars=20000: ExtractionResult(
            clean_text="",
            source="html_article",
            error="heuristic_empty",
        ),
    )
    monkeypatch.setattr(module, "playwright_extract_content", lambda *args, **kwargs: ExtractionResult("", "playwright"))

    result = fetch_article_content(
        article,
        requester=SimpleNamespace(get=lambda *args, **kwargs: _response(_fixture("low_quality_page.html"))),
        playwright_fallback=False,
    )

    assert result.content_status == "low_quality"
    assert result.clean_text == ""
    assert result.content_source == "trafilatura"
    assert "quality=" in result.content_error


def test_fetch_article_content_uses_playwright_fallback(monkeypatch):
    article = _article()
    import products.tech_blog_monitor.content_fetcher as module

    monkeypatch.setattr(
        module,
        "trafilatura_extract_content",
        lambda html_text, *, url="", max_chars=20000: ExtractionResult(
            clean_text="",
            source="trafilatura",
            error="trafilatura_empty",
        ),
    )
    monkeypatch.setattr(
        module,
        "heuristic_extract_content",
        lambda html_text, *, url="", max_chars=20000: ExtractionResult(
            clean_text="",
            source="html_article",
            error="heuristic_empty",
        ),
    )
    monkeypatch.setattr(
        module,
        "playwright_extract_content",
        lambda url, *, timeout_ms, max_chars: ExtractionResult(
            clean_text=(
                "Rendered content after browser execution.\n\n"
                "This page now contains the full article body for testing."
            ),
            source="playwright_trafilatura",
        ),
    )

    html_text = """
    <html>
      <head><script>window.__NEXT_DATA__ = {};</script></head>
      <body><div id="root"></div><script src="/app.js"></script></body>
    </html>
    """
    result = fetch_article_content(
        article,
        requester=SimpleNamespace(get=lambda *args, **kwargs: _response(html_text)),
        playwright_fallback=True,
        playwright_timeout=7,
        playwright_workers=1,
    )

    assert result.content_status == "fetched"
    assert result.content_source == "playwright_trafilatura"
    assert "Rendered content" in result.clean_text


def test_fetch_contents_preserves_order():
    articles = [_article(url="https://example.com/a"), _article(url="https://example.com/b")]
    html_by_url = {
        "https://example.com/a": _fixture("article_page.html"),
        "https://example.com/b": _fixture("json_ld_page.html"),
    }

    def fake_get(url, **kwargs):
        return _response(html_by_url[url], url=url)

    # fetch_contents 内部会调用 fetch_article_content -> requests.get，
    # 这里直接通过 monkeypatch 替换模块级 requests.get 更贴近实际路径。
    import products.tech_blog_monitor.content_fetcher as module

    original_get = module.requests.get
    module.requests.get = fake_get
    try:
        results = fetch_contents(
            articles,
            workers=2,
            timeout=5,
            max_chars=500,
            content_extractor="heuristic",
            playwright_fallback=False,
        )
    finally:
        module.requests.get = original_get

    assert [article.url for article in results] == ["https://example.com/a", "https://example.com/b"]
    assert results[0].content_status == "fetched"
    assert results[1].content_status == "fetched"
