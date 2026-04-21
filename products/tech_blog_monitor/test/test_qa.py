# -*- coding: utf-8 -*-
"""Tech Blog Monitor Phase 5 QA / retrieval tests."""

from datetime import datetime, timezone

import pytest

from products.tech_blog_monitor.archive_store import ArchiveStore
from products.tech_blog_monitor.db.engine import build_sqlite_url, create_session_factory
from products.tech_blog_monitor.db.models import ChunkEmbeddingRecordModel
from products.tech_blog_monitor.db.repositories.retrieval_repository import RetrievalRepository
from products.tech_blog_monitor.db.schema_manager import bootstrap_schema
from products.tech_blog_monitor.fetcher import Article
from products.tech_blog_monitor.observability.metrics import (
    get_default_metrics_registry,
    reset_default_metrics_registry,
)
from products.tech_blog_monitor.qa import answer_question, format_qa_result
from products.tech_blog_monitor.qa_cli import main as qa_cli_main
from products.tech_blog_monitor.retrieval import (
    OpenAICompatibleEmbeddingProvider,
    RetrievalQuery,
    build_fake_embedding,
    cosine_similarity,
    rank_chunks,
    resolve_embedding_provider,
)


def _article(
    title: str,
    url: str,
    source_name: str,
    category: str,
    published_ts: int,
    rss_summary: str = "",
    clean_text: str = "",
    topic: str = "",
    tags: list[str] | None = None,
    why_it_matters: str = "",
):
    published = datetime.fromtimestamp(published_ts, tz=timezone.utc)
    article = Article(
        title=title,
        url=url,
        source_name=source_name,
        category=category,
        source_id=f"{source_name}::{url}",
        rss_summary=rss_summary,
        published=published,
        published_ts=published_ts,
        fetched_at=published_ts,
        clean_text=clean_text,
        content_status="fetched" if clean_text else "not_fetched",
        content_source="html_article" if clean_text else "",
    )
    article.one_line_summary = f"{title} summary"
    article.why_it_matters = why_it_matters or f"{title} matters"
    article.topic = topic
    article.tags = list(tags or [])
    article.key_points = [f"{title} point"]
    article.recommended_for = ["工程师"]
    article.enrichment_status = "enriched"
    return article


def _build_store(tmp_path):
    db_path = tmp_path / "assets.db"
    articles = [
        _article(
            title="Agent Memory Systems",
            url="https://example.com/agent-memory",
            source_name="OpenAI News",
            category="AI Agent/工程实践",
            published_ts=1744588800,
            rss_summary="Agent memory summary",
            clean_text=(
                "Agent memory systems store long-running task context, retrieval state, "
                "and tool outputs so the workflow can continue across sessions."
            ),
            topic="智能体",
            tags=["agent", "memory"],
            why_it_matters="Useful for durable agent workflows.",
        ),
        _article(
            title="Inference Batching Design",
            url="https://example.com/inference-batching",
            source_name="NVIDIA Technical Blog",
            category="深度技术",
            published_ts=1744502400,
            rss_summary="Inference batching summary",
            clean_text=(
                "Inference batching improves throughput by grouping requests, managing "
                "GPU utilization, and scheduling latency-sensitive traffic."
            ),
            topic="基础设施",
            tags=["inference", "gpu"],
            why_it_matters="Relevant for serving systems.",
        ),
        _article(
            title="Safety Evaluation Benchmarks",
            url="https://example.com/safety-eval",
            source_name="DeepMind",
            category="行业风向标",
            published_ts=1744416000,
            rss_summary="Safety benchmark summary",
            clean_text=(
                "Safety evaluations compare benchmark coverage, jailbreak robustness, "
                "and monitoring quality across model versions."
            ),
            topic="评测",
            tags=["safety", "evaluation"],
            why_it_matters="Relevant for release governance.",
        ),
    ]

    with ArchiveStore(str(db_path)) as store:
        store.record_run(
            generated_at=1744675200,
            generated_at_iso="2025-04-15T00:00:00+00:00",
            output_path="/tmp/report.md",
            view="by_category",
            incremental_mode="split",
            all_articles=articles,
            report_articles=articles,
            new_urls={articles[0].url},
        )
    return str(db_path)


def test_fake_embedding_is_deterministic():
    left = build_fake_embedding("agent memory systems")
    right = build_fake_embedding("agent memory systems")
    other = build_fake_embedding("gpu inference systems")
    assert left == right
    assert cosine_similarity(left, right) == pytest.approx(1.0)
    assert cosine_similarity(left, other) < 1.0


def test_rank_chunks_prefers_relevant_candidate():
    ranked = rank_chunks(
        "What changed in agent memory workflows?",
        [
            {
                "article_id": "a",
                "chunk_id": "a:0",
                "chunk_index": 0,
                "title": "Agent Memory Systems",
                "url": "https://example.com/a",
                "source_name": "OpenAI",
                "category": "AI",
                "topic": "智能体",
                "published_ts": 100,
                "text": "Agent memory workflows store long-running context and retrieval state.",
                "source_kind": "clean_text",
                "embedding": build_fake_embedding(
                    "Agent memory workflows store long-running context and retrieval state."
                ),
                "tags": ["agent", "memory"],
                "one_line_summary": "memory summary",
                "why_it_matters": "important",
            },
            {
                "article_id": "b",
                "chunk_id": "b:0",
                "chunk_index": 0,
                "title": "GPU Batching",
                "url": "https://example.com/b",
                "source_name": "NVIDIA",
                "category": "Infra",
                "topic": "基础设施",
                "published_ts": 90,
                "text": "GPU batching changes throughput and queueing efficiency.",
                "source_kind": "clean_text",
                "embedding": build_fake_embedding("GPU batching changes throughput and queueing efficiency."),
                "tags": ["gpu"],
                "one_line_summary": "batching summary",
                "why_it_matters": "important",
            },
        ],
        limit=2,
    )
    assert ranked[0].title == "Agent Memory Systems"
    assert ranked[0].lexical_score > ranked[1].lexical_score
    assert ranked[0].semantic_score >= ranked[1].semantic_score


def test_openai_compatible_embedding_provider_uses_mocked_session():
    class _DummyResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "data": [
                    {"index": 1, "embedding": [0.3, 0.4]},
                    {"index": 0, "embedding": [0.1, 0.2]},
                ]
            }

    class _DummySession:
        def __init__(self):
            self.calls = []

        def post(self, url, headers=None, json=None, timeout=None):
            self.calls.append((url, headers, json, timeout))
            return _DummyResponse()

    session = _DummySession()
    provider = OpenAICompatibleEmbeddingProvider(
        api_key="test-key",
        model="text-embedding-test",
        base_url="https://example.com/v1",
        session=session,
    )

    embeddings = provider.embed_texts(["first", "second"])

    assert embeddings == [[0.1, 0.2], [0.3, 0.4]]
    assert session.calls[0][0] == "https://example.com/v1/embeddings"
    assert session.calls[0][2]["input"] == ["first", "second"]


def test_resolve_embedding_provider_falls_back_to_fake(monkeypatch):
    monkeypatch.setenv("TECH_BLOG_EMBEDDING_PROVIDER", "openai_compatible")
    monkeypatch.delenv("TECH_BLOG_EMBEDDING_API_KEY", raising=False)
    monkeypatch.delenv("TECH_BLOG_EMBEDDING_MODEL", raising=False)

    resolution = resolve_embedding_provider()

    assert resolution.requested_provider_name == "openai_compatible"
    assert resolution.active_provider_name == "fake"
    assert "missing TECH_BLOG_EMBEDDING_API_KEY" in resolution.fallback_reason


def test_answer_question_returns_cited_evidence(tmp_path):
    db_path = _build_store(tmp_path)
    result = answer_question(
        db_path,
        RetrievalQuery(question="哪些文章讨论了 agent memory?", limit=2),
    )
    assert result.status == "answered"
    assert result.citations
    assert "Agent Memory Systems" in result.answer
    cited_urls = {citation.url for citation in result.citations}
    retrieved_urls = {chunk.url for chunk in result.retrieved_chunks}
    assert cited_urls == retrieved_urls
    assert cited_urls == {"https://example.com/agent-memory"}


def test_answer_question_falls_back_when_real_provider_is_unavailable(monkeypatch, tmp_path):
    monkeypatch.setenv("TECH_BLOG_EMBEDDING_PROVIDER", "openai_compatible")
    monkeypatch.delenv("TECH_BLOG_EMBEDDING_API_KEY", raising=False)
    monkeypatch.delenv("TECH_BLOG_EMBEDDING_MODEL", raising=False)
    db_path = _build_store(tmp_path)

    result = answer_question(
        db_path,
        RetrievalQuery(question="哪些文章讨论了 agent memory?", limit=2),
    )

    assert result.status == "answered"
    assert result.citations[0].url == "https://example.com/agent-memory"


def test_answer_question_refuses_without_evidence(tmp_path):
    db_path = _build_store(tmp_path)
    result = answer_question(
        db_path,
        RetrievalQuery(question="量子纠缠芯片什么时候发布?", limit=2),
    )
    assert result.status == "insufficient_evidence"
    assert result.citations == []
    assert "无法可靠回答" in result.answer


def test_answer_question_records_latency_metric(tmp_path):
    reset_default_metrics_registry()
    db_path = _build_store(tmp_path)

    result = answer_question(
        db_path,
        RetrievalQuery(question="哪些文章讨论了 agent memory?", limit=2),
    )

    assert result.status == "answered"
    snapshot = get_default_metrics_registry().snapshot()
    assert snapshot["histograms"]["qa_latency_ms"]["count"] == 1


def test_format_qa_result_contains_citations(tmp_path):
    db_path = _build_store(tmp_path)
    result = answer_question(
        db_path,
        RetrievalQuery(question="GPU batching 有什么变化?", limit=2),
    )
    text = format_qa_result(result)
    assert "出处：" in text
    for citation in result.citations:
        assert citation.url in text


def test_qa_cli_missing_db_exits_nonzero(monkeypatch, tmp_path, capsys):
    missing = tmp_path / "missing.db"
    monkeypatch.setattr(
        "sys.argv",
        ["qa_cli.py", "--db", str(missing), "--question", "agent memory"],
    )

    with pytest.raises(SystemExit) as exc:
        qa_cli_main()

    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "资产库不存在" in captured.err


def test_answer_question_uses_database_url_when_provided(tmp_path):
    db_path = _build_store(tmp_path)
    result = answer_question(
        str(tmp_path / "missing.db"),
        RetrievalQuery(question="哪些文章讨论了 agent memory?", limit=2),
        database_url=build_sqlite_url(db_path),
    )
    assert result.status == "answered"
    assert result.citations[0].url == "https://example.com/agent-memory"


def test_postgres_retrieval_does_not_require_lexical_overlap(tmp_path):
    question = "How do autonomous workflow coordinators retain history?"
    database_url = build_sqlite_url(str(tmp_path / "vector.db"))
    bootstrap_schema(database_url)

    session_factory = create_session_factory(database_url)
    with session_factory() as session:
        session.merge(
            ChunkEmbeddingRecordModel(
                chunk_id="semantic:0",
                article_id="semantic",
                chunk_index=0,
                title="Durable Planner State",
                url="https://example.com/semantic",
                source_name="OpenAI News",
                category="AI Agent/工程实践",
                topic="智能体",
                published_ts=1744588800,
                source_kind="clean_text",
                text="Persistent planner state survives across turns and sessions.",
                document_text="Persistent planner state survives across turns and sessions.",
                embedding_json=build_fake_embedding(question),
                embedding_vector=build_fake_embedding(question),
                updated_at=1744588800,
            )
        )
        session.merge(
            ChunkEmbeddingRecordModel(
                chunk_id="lexical:0",
                article_id="lexical",
                chunk_index=0,
                title="Coordinator Keywords",
                url="https://example.com/lexical",
                source_name="Other Source",
                category="其他",
                topic="其他",
                published_ts=1744588700,
                source_kind="clean_text",
                text="Coordinator workflow notes without the right vector signal.",
                document_text="Coordinator workflow notes without the right vector signal.",
                embedding_json=[0.0] * 64,
                embedding_vector=[0.0] * 64,
                updated_at=1744588700,
            )
        )
        session.commit()

    with session_factory() as session:
        repository = RetrievalRepository(session)
        repository.dialect_name = "postgresql"
        rows = repository.retrieve_chunks(question=question, limit=1)

    assert rows[0]["chunk_id"] == "semantic:0"
    assert rows[0]["url"] == "https://example.com/semantic"
