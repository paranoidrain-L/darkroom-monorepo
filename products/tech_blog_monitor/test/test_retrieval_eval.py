# -*- coding: utf-8 -*-
"""Offline retrieval evaluation baseline for Tech Blog Monitor."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from products.tech_blog_monitor.retrieval import (
    LEGACY_RANKING_CONFIG,
    build_fake_embedding,
    compute_retrieval_metrics,
    dedupe_by_article,
    lexical_overlap_score,
    rank_chunks,
)

_FIXTURE_DIR = Path(__file__).parent / "fixtures"
_CORPUS_PATH = _FIXTURE_DIR / "retrieval_eval_corpus.json"
_QUERIES_PATH = _FIXTURE_DIR / "retrieval_eval_queries.json"


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _load_corpus():
    rows = _load_json(_CORPUS_PATH)
    corpus = []
    for row in rows:
        candidate = dict(row)
        embedding_hint = str(candidate.pop("embedding_hint", "") or "")
        if embedding_hint:
            candidate["embedding"] = build_fake_embedding(embedding_hint)
        corpus.append(candidate)
    return corpus


def _rank_article_ids(
    question: str,
    corpus: list[dict[str, object]],
    *,
    ranking_config=None,
    embedding_provider_name: str | None = None,
) -> list[str]:
    ranked = rank_chunks(
        question,
        corpus,
        limit=len(corpus),
        ranking_config=ranking_config,
        embedding_provider_name=embedding_provider_name,
    )
    return [chunk.article_id for chunk in dedupe_by_article(ranked)]


def _document_text(candidate: dict[str, object]) -> str:
    parts = [
        str(candidate.get("title", "") or ""),
        str(candidate.get("topic", "") or ""),
        str(candidate.get("one_line_summary", "") or ""),
        str(candidate.get("why_it_matters", "") or ""),
        str(candidate.get("rss_summary", "") or ""),
        str(candidate.get("text", "") or ""),
    ]
    tags = candidate.get("tags") or []
    if isinstance(tags, list):
        parts.extend(str(tag) for tag in tags if isinstance(tag, str))
    return "\n".join(part for part in parts if part)


def _compute_eval_metrics(corpus: list[dict[str, object]], query_rows, *, ranking_config=None):
    ranked_article_ids_by_query = {
        row["query_id"]: _rank_article_ids(
            row["query"],
            corpus,
            ranking_config=ranking_config,
        )
        for row in query_rows
    }
    relevant_article_ids_by_query = {
        row["query_id"]: row["relevant_article_ids"]
        for row in query_rows
    }
    return compute_retrieval_metrics(
        ranked_article_ids_by_query,
        relevant_article_ids_by_query,
        ks=(1, 3, 5),
    )


def test_retrieval_eval_hybrid_improves_on_legacy_baseline():
    corpus = _load_corpus()
    query_rows = _load_json(_QUERIES_PATH)
    legacy_metrics = _compute_eval_metrics(
        corpus,
        query_rows,
        ranking_config=LEGACY_RANKING_CONFIG,
    )
    hybrid_metrics = _compute_eval_metrics(corpus, query_rows)
    legacy_per_query = {item["query_id"]: item for item in legacy_metrics["per_query"]}
    hybrid_per_query = {item["query_id"]: item for item in hybrid_metrics["per_query"]}
    relative_mrr_uplift = (
        (hybrid_metrics["mrr"] - legacy_metrics["mrr"]) / legacy_metrics["mrr"]
        if legacy_metrics["mrr"] > 0
        else 0.0
    )

    assert legacy_metrics["query_count"] == 7
    assert legacy_metrics["hit_at_k"][1] == pytest.approx(5 / 7)
    assert legacy_metrics["hit_at_k"][3] == pytest.approx(1.0)
    assert legacy_metrics["recall_at_k"][1] == pytest.approx(9 / 14)
    assert legacy_metrics["mrr"] == pytest.approx(6 / 7)
    assert legacy_per_query["hard_release_checklist"]["first_relevant_rank"] == 2
    assert legacy_per_query["release_holds"]["first_relevant_rank"] == 2

    assert hybrid_metrics["query_count"] == 7
    assert hybrid_metrics["hit_at_k"][1] == pytest.approx(1.0)
    assert hybrid_metrics["hit_at_k"][5] >= legacy_metrics["hit_at_k"][5]
    assert hybrid_metrics["mrr"] == pytest.approx(1.0)
    assert relative_mrr_uplift >= 0.15
    assert hybrid_per_query["weak_lexical_history"]["first_relevant_rank"] == 1
    assert hybrid_per_query["hard_release_checklist"]["first_relevant_rank"] == 1
    assert hybrid_per_query["release_holds"]["first_relevant_rank"] == 1


def test_retrieval_eval_covers_weak_lexical_and_source_aware_queries():
    corpus = _load_corpus()
    query_rows = {row["query_id"]: row for row in _load_json(_QUERIES_PATH)}
    corpus_by_article_id = {
        str(row["article_id"]): row
        for row in _load_json(_CORPUS_PATH)
    }

    weak_lexical_ranked = _rank_article_ids(
        query_rows["weak_lexical_history"]["query"],
        corpus,
    )
    source_aware_ranked = _rank_article_ids(
        query_rows["source_openai_workflow"]["query"],
        corpus,
    )
    why_compare_ranked = _rank_article_ids(
        query_rows["why_compare_safety_governance"]["query"],
        corpus,
    )
    hard_release_ranked = _rank_article_ids(
        query_rows["hard_release_checklist"]["query"],
        corpus,
    )
    hard_release_ranked_legacy = _rank_article_ids(
        query_rows["hard_release_checklist"]["query"],
        corpus,
        ranking_config=LEGACY_RANKING_CONFIG,
    )
    release_holds_ranked = _rank_article_ids(
        query_rows["release_holds"]["query"],
        corpus,
    )
    release_holds_ranked_legacy = _rank_article_ids(
        query_rows["release_holds"]["query"],
        corpus,
        ranking_config=LEGACY_RANKING_CONFIG,
    )
    weak_lexical_score = lexical_overlap_score(
        query_rows["weak_lexical_history"]["query"],
        _document_text(corpus_by_article_id["agent_memory"]),
    )

    assert weak_lexical_ranked[0] == "agent_memory"
    assert weak_lexical_score == pytest.approx(0.0)
    assert source_aware_ranked[0] == "durable_workflow"
    assert why_compare_ranked[:2] == ["safety_benchmarks", "release_checklists"]
    assert hard_release_ranked[0] == "release_checklists"
    assert hard_release_ranked_legacy[:2] == ["safety_benchmarks", "release_checklists"]
    assert release_holds_ranked[0] == "release_checklists"
    assert release_holds_ranked_legacy[:2] == ["safety_benchmarks", "release_checklists"]
