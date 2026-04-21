# -*- coding: utf-8 -*-
"""Tech Blog Monitor - Phase 5 基础问答服务。"""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import List

from products.tech_blog_monitor.observability.metrics import get_default_metrics_registry
from products.tech_blog_monitor.repository_provider import open_repository_bundle
from products.tech_blog_monitor.retrieval import (
    RetrievalQuery,
    RetrievedChunk,
    dedupe_by_article,
    get_configured_embedding_provider_name,
    rank_chunks,
)

_MIN_EVIDENCE_SCORE = 1.2
_MAX_EVIDENCE_CHARS = 220


@dataclass
class Citation:
    title: str
    url: str
    source_name: str
    chunk_id: str


@dataclass
class QAResult:
    answer: str
    citations: List[Citation]
    retrieved_chunks: List[RetrievedChunk]
    status: str


def _trim_evidence(text: str, limit: int = _MAX_EVIDENCE_CHARS) -> str:
    stripped = " ".join(text.split())
    if len(stripped) <= limit:
        return stripped
    return stripped[: limit - 1].rstrip() + "…"


def _build_answer(question: str, evidence_chunks: List[RetrievedChunk]) -> str:
    lines = [f"问题：{question}", "", "基于命中文章，当前可以确认："]
    for index, chunk in enumerate(evidence_chunks, start=1):
        topic_text = f"；主题：{chunk.topic}" if chunk.topic else ""
        lines.append(
            f"{index}. {chunk.title}（{chunk.source_name}{topic_text}）: {_trim_evidence(chunk.text)}"
        )
    return "\n".join(lines)


def answer_question(db_path: str, query: RetrievalQuery, *, database_url: str = "") -> QAResult:
    started = perf_counter()
    status = "success"
    provider_name = get_configured_embedding_provider_name()
    try:
        with open_repository_bundle(asset_db_path=db_path, database_url=database_url) as bundle:
            candidates = bundle.retrieval_repository.retrieve_chunks(
                question=query.question,
                limit=query.candidate_limit,
                embedding_provider_name=provider_name,
            )
            if not candidates:
                candidates = bundle.retrieval_repository.retrieve_chunks(
                    question="",
                    limit=query.candidate_limit,
                    embedding_provider_name=provider_name,
                )

        ranked = rank_chunks(
            query.question,
            candidates,
            limit=query.candidate_limit,
            embedding_provider_name=provider_name,
        )
        evidence_chunks = [
            chunk for chunk in dedupe_by_article(ranked)
            if chunk.score >= _MIN_EVIDENCE_SCORE
        ][: query.limit]

        if not evidence_chunks:
            status = "insufficient_evidence"
            return QAResult(
                answer="未检索到足够证据，当前无法可靠回答该问题。",
                citations=[],
                retrieved_chunks=[],
                status="insufficient_evidence",
            )

        citations = [
            Citation(
                title=chunk.title,
                url=chunk.url,
                source_name=chunk.source_name,
                chunk_id=chunk.chunk_id,
            )
            for chunk in evidence_chunks
        ]
        return QAResult(
            answer=_build_answer(query.question, evidence_chunks),
            citations=citations,
            retrieved_chunks=evidence_chunks,
            status="answered",
        )
    except Exception:
        status = "failed"
        raise
    finally:
        get_default_metrics_registry().observe_qa_latency(
            (perf_counter() - started) * 1000,
            dimensions={
                "status": status,
                "has_database_url": bool(database_url),
            },
        )


def format_qa_result(result: QAResult) -> str:
    lines = [result.answer]
    if result.citations:
        lines.append("")
        lines.append("出处：")
        for index, citation in enumerate(result.citations, start=1):
            lines.append(
                f"{index}. {citation.title} | {citation.source_name} | {citation.url}"
            )
    return "\n".join(lines)
