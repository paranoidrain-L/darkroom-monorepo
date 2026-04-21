# -*- coding: utf-8 -*-
"""Tech Blog Monitor - hybrid retrieval and evaluation helpers."""

from __future__ import annotations

import hashlib
import math
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Sequence

import requests

_TOKEN_RE = re.compile(r"[A-Za-z0-9_+/.-]+|[\u4e00-\u9fff]{1,8}")
_EMBEDDING_DIM = 64
_DEFAULT_CANDIDATE_LIMIT = 25
_DEFAULT_EMBEDDING_PROVIDER = "fake"


@dataclass
class RetrievalQuery:
    question: str
    limit: int = 5
    candidate_limit: int = _DEFAULT_CANDIDATE_LIMIT


@dataclass
class RankingConfig:
    lexical_weight: float = 1.25
    semantic_weight: float = 2.0
    title_weight: float = 1.6
    topic_weight: float = 0.8
    summary_weight: float = 0.9
    why_weight: float = 0.8
    text_weight: float = 0.45
    tags_weight: float = 1.1
    freshness_bonus: float = 0.05
    normalize_lexical: bool = True
    clamp_semantic_to_zero: bool = True
    field_weighted_lexical: bool = True


LEGACY_RANKING_CONFIG = RankingConfig(
    lexical_weight=1.0,
    semantic_weight=1.0,
    title_weight=1.0,
    topic_weight=1.0,
    summary_weight=1.0,
    why_weight=1.0,
    text_weight=1.0,
    tags_weight=1.0,
    freshness_bonus=0.05,
    normalize_lexical=False,
    clamp_semantic_to_zero=False,
    field_weighted_lexical=False,
)

DEFAULT_HYBRID_RANKING_CONFIG = RankingConfig()


@dataclass
class RetrievedChunk:
    article_id: str
    chunk_id: str
    chunk_index: int
    title: str
    url: str
    source_name: str
    category: str
    topic: str
    published_ts: int | None
    text: str
    source_kind: str
    lexical_score: float
    semantic_score: float
    freshness_bonus: float
    final_score: float
    embedding_provider: str = _DEFAULT_EMBEDDING_PROVIDER

    @property
    def vector_score(self) -> float:
        return self.semantic_score

    @property
    def score(self) -> float:
        return self.final_score


@dataclass
class EmbeddingProviderResolution:
    requested_provider_name: str
    active_provider_name: str
    provider: "EmbeddingProvider"
    fallback_reason: str = ""


class EmbeddingProviderError(RuntimeError):
    """Raised when an optional embedding backend is unavailable."""


class EmbeddingProvider:
    name = "unknown"

    def is_available(self) -> bool:
        return True

    def embed_texts(self, texts: Sequence[str]) -> List[List[float]]:
        raise NotImplementedError


class FakeEmbeddingProvider(EmbeddingProvider):
    name = "fake"

    def embed_texts(self, texts: Sequence[str]) -> List[List[float]]:
        return [build_fake_embedding(text) for text in texts]


class OpenAICompatibleEmbeddingProvider(EmbeddingProvider):
    name = "openai_compatible"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str,
        timeout_sec: float = 10.0,
        session: requests.Session | None = None,
    ) -> None:
        self.api_key = api_key.strip()
        self.model = model.strip()
        self.base_url = base_url.rstrip("/")
        self.timeout_sec = timeout_sec
        self._session = session or requests.Session()

    def is_available(self) -> bool:
        return bool(self.api_key and self.model and self.base_url)

    def embed_texts(self, texts: Sequence[str]) -> List[List[float]]:
        if not texts:
            return []
        if not self.is_available():
            raise EmbeddingProviderError(
                "openai_compatible embedding provider is unavailable: "
                "missing TECH_BLOG_EMBEDDING_API_KEY or TECH_BLOG_EMBEDDING_MODEL"
            )

        try:
            response = self._session.post(
                f"{self.base_url}/embeddings",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "input": list(texts),
                },
                timeout=self.timeout_sec,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:  # pragma: no cover - exercised via fallback tests
            raise EmbeddingProviderError(
                f"openai_compatible embedding request failed: {exc}"
            ) from exc

        data = payload.get("data")
        if not isinstance(data, list):
            raise EmbeddingProviderError("openai_compatible embedding response missing data list")

        embeddings = [item.get("embedding") for item in sorted(data, key=lambda item: item.get("index", 0))]
        if len(embeddings) != len(texts) or any(not isinstance(item, list) for item in embeddings):
            raise EmbeddingProviderError("openai_compatible embedding response is malformed")
        return [[float(value) for value in embedding] for embedding in embeddings]


def tokenize(text: str) -> List[str]:
    return [token.lower() for token in _TOKEN_RE.findall(text or "")]


def build_fake_embedding(text: str, *, dims: int = _EMBEDDING_DIM) -> List[float]:
    vector = [0.0] * dims
    tokens = tokenize(text)
    if not tokens:
        return vector

    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        bucket = int.from_bytes(digest[:4], "big") % dims
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[bucket] += sign

    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right))


def lexical_overlap_score(query_text: str, candidate_text: str) -> float:
    query_tokens = set(tokenize(query_text))
    if not query_tokens:
        return 0.0

    candidate_tokens = tokenize(candidate_text)
    if not candidate_tokens:
        return 0.0

    matched = sum(1 for token in candidate_tokens if token in query_tokens)
    unique_matches = len(query_tokens.intersection(candidate_tokens))
    return unique_matches * 3.0 + matched * 0.2


def get_configured_embedding_provider_name() -> str:
    provider_name = os.environ.get("TECH_BLOG_EMBEDDING_PROVIDER", _DEFAULT_EMBEDDING_PROVIDER)
    normalized = provider_name.strip().lower()
    return normalized or _DEFAULT_EMBEDDING_PROVIDER


def resolve_embedding_provider(
    provider_name: str | None = None,
) -> EmbeddingProviderResolution:
    requested_provider_name = (provider_name or get_configured_embedding_provider_name()).strip().lower()
    if not requested_provider_name or requested_provider_name == _DEFAULT_EMBEDDING_PROVIDER:
        provider = FakeEmbeddingProvider()
        return EmbeddingProviderResolution(
            requested_provider_name=_DEFAULT_EMBEDDING_PROVIDER,
            active_provider_name=provider.name,
            provider=provider,
        )

    if requested_provider_name == OpenAICompatibleEmbeddingProvider.name:
        provider = OpenAICompatibleEmbeddingProvider(
            api_key=os.environ.get("TECH_BLOG_EMBEDDING_API_KEY", ""),
            model=os.environ.get("TECH_BLOG_EMBEDDING_MODEL", ""),
            base_url=os.environ.get("TECH_BLOG_EMBEDDING_BASE_URL", "https://api.openai.com/v1"),
            timeout_sec=float(os.environ.get("TECH_BLOG_EMBEDDING_TIMEOUT_SEC", "10.0") or "10.0"),
        )
        if provider.is_available():
            return EmbeddingProviderResolution(
                requested_provider_name=requested_provider_name,
                active_provider_name=provider.name,
                provider=provider,
            )
        return EmbeddingProviderResolution(
            requested_provider_name=requested_provider_name,
            active_provider_name=_DEFAULT_EMBEDDING_PROVIDER,
            provider=FakeEmbeddingProvider(),
            fallback_reason=(
                "openai_compatible embedding provider is unavailable: "
                "missing TECH_BLOG_EMBEDDING_API_KEY or TECH_BLOG_EMBEDDING_MODEL"
            ),
        )

    return EmbeddingProviderResolution(
        requested_provider_name=requested_provider_name,
        active_provider_name=_DEFAULT_EMBEDDING_PROVIDER,
        provider=FakeEmbeddingProvider(),
        fallback_reason=f"unknown embedding provider: {requested_provider_name}",
    )


def _candidate_field_values(candidate: Mapping[str, object]) -> Dict[str, str]:
    tags = candidate.get("tags") or []
    tag_text = ""
    if isinstance(tags, list):
        tag_text = " ".join(str(tag) for tag in tags if isinstance(tag, str))
    return {
        "title": str(candidate.get("title", "") or ""),
        "topic": str(candidate.get("topic", "") or ""),
        "summary": str(candidate.get("one_line_summary", "") or ""),
        "why": str(candidate.get("why_it_matters", "") or ""),
        "text": str(candidate.get("text", "") or ""),
        "tags": tag_text,
    }


def _candidate_document_text(candidate: Mapping[str, object]) -> str:
    fields = _candidate_field_values(candidate)
    rss_summary = str(candidate.get("rss_summary", "") or "")
    parts = [
        fields["title"],
        fields["topic"],
        fields["summary"],
        fields["why"],
        rss_summary,
        fields["text"],
        fields["tags"],
    ]
    return "\n".join(part for part in parts if part)


def _field_weighted_lexical_score(
    question: str,
    candidate: Mapping[str, object],
    *,
    config: RankingConfig,
) -> float:
    if not config.field_weighted_lexical:
        return lexical_overlap_score(question, _candidate_document_text(candidate))

    fields = _candidate_field_values(candidate)
    raw_score = (
        lexical_overlap_score(question, fields["title"]) * config.title_weight
        + lexical_overlap_score(question, fields["topic"]) * config.topic_weight
        + lexical_overlap_score(question, fields["summary"]) * config.summary_weight
        + lexical_overlap_score(question, fields["why"]) * config.why_weight
        + lexical_overlap_score(question, fields["text"]) * config.text_weight
        + lexical_overlap_score(question, fields["tags"]) * config.tags_weight
    )
    if config.normalize_lexical:
        return math.log1p(raw_score)
    return raw_score


def _serialize_fake_candidate_embedding(
    candidate: Mapping[str, object],
    document_text: str,
) -> List[float]:
    embedding = candidate.get("embedding")
    if isinstance(embedding, list) and embedding:
        return [float(value) for value in embedding]
    return build_fake_embedding(document_text)


def _embed_query_text(
    question: str,
    resolution: EmbeddingProviderResolution,
) -> tuple[List[float], EmbeddingProviderResolution]:
    if not question.strip():
        return [], resolution
    if resolution.active_provider_name == _DEFAULT_EMBEDDING_PROVIDER:
        return build_fake_embedding(question), resolution

    try:
        return resolution.provider.embed_texts([question])[0], resolution
    except EmbeddingProviderError as exc:
        return (
            build_fake_embedding(question),
            EmbeddingProviderResolution(
                requested_provider_name=resolution.requested_provider_name,
                active_provider_name=_DEFAULT_EMBEDDING_PROVIDER,
                provider=FakeEmbeddingProvider(),
                fallback_reason=str(exc),
            ),
        )


def _embed_candidate_texts(
    candidates: Sequence[Mapping[str, object]],
    document_texts: Sequence[str],
    resolution: EmbeddingProviderResolution,
) -> tuple[List[List[float]], EmbeddingProviderResolution]:
    if resolution.active_provider_name == _DEFAULT_EMBEDDING_PROVIDER:
        return [
            _serialize_fake_candidate_embedding(candidate, document_text)
            for candidate, document_text in zip(candidates, document_texts)
        ], resolution

    try:
        return resolution.provider.embed_texts(document_texts), resolution
    except EmbeddingProviderError as exc:
        return (
            [
                _serialize_fake_candidate_embedding(candidate, document_text)
                for candidate, document_text in zip(candidates, document_texts)
            ],
            EmbeddingProviderResolution(
                requested_provider_name=resolution.requested_provider_name,
                active_provider_name=_DEFAULT_EMBEDDING_PROVIDER,
                provider=FakeEmbeddingProvider(),
                fallback_reason=str(exc),
            ),
        )


def rank_chunks(
    question: str,
    candidates: Sequence[Dict[str, object]],
    *,
    limit: int = 5,
    embedding_provider_name: str | None = None,
    ranking_config: RankingConfig | None = None,
) -> List[RetrievedChunk]:
    config = ranking_config or DEFAULT_HYBRID_RANKING_CONFIG
    resolution = resolve_embedding_provider(embedding_provider_name)
    document_texts = [_candidate_document_text(candidate) for candidate in candidates]
    query_embedding, resolution = _embed_query_text(question, resolution)
    candidate_embeddings, resolution = _embed_candidate_texts(candidates, document_texts, resolution)

    ranked: List[RetrievedChunk] = []
    for candidate, document_text, candidate_embedding in zip(candidates, document_texts, candidate_embeddings):
        text = str(candidate.get("text", "") or "")
        lexical_score = _field_weighted_lexical_score(question, candidate, config=config)
        semantic_score = cosine_similarity(query_embedding, candidate_embedding)
        if config.clamp_semantic_to_zero:
            semantic_score = max(semantic_score, 0.0)
        freshness_bonus = 0.0 if candidate.get("published_ts") is None else config.freshness_bonus
        final_score = (
            lexical_score * config.lexical_weight
            + semantic_score * config.semantic_weight
            + freshness_bonus
        )
        ranked.append(
            RetrievedChunk(
                article_id=str(candidate.get("article_id", "")),
                chunk_id=str(candidate.get("chunk_id", "")),
                chunk_index=int(candidate.get("chunk_index", 0) or 0),
                title=str(candidate.get("title", "")),
                url=str(candidate.get("url", "")),
                source_name=str(candidate.get("source_name", "")),
                category=str(candidate.get("category", "")),
                topic=str(candidate.get("topic", "")),
                published_ts=(
                    int(candidate["published_ts"])
                    if isinstance(candidate.get("published_ts"), int)
                    else None
                ),
                text=text,
                source_kind=str(candidate.get("source_kind", "")),
                lexical_score=lexical_score,
                semantic_score=semantic_score,
                freshness_bonus=freshness_bonus,
                final_score=final_score,
                embedding_provider=resolution.active_provider_name,
            )
        )

    ranked.sort(
        key=lambda item: (
            item.final_score,
            item.semantic_score,
            item.lexical_score,
            item.published_ts or 0,
            -item.chunk_index,
        ),
        reverse=True,
    )
    return ranked[:limit]


def dedupe_by_article(chunks: Iterable[RetrievedChunk]) -> List[RetrievedChunk]:
    seen: set[str] = set()
    deduped: List[RetrievedChunk] = []
    for chunk in chunks:
        if chunk.article_id in seen:
            continue
        seen.add(chunk.article_id)
        deduped.append(chunk)
    return deduped


def compute_retrieval_metrics(
    ranked_article_ids_by_query: Mapping[str, Sequence[str]],
    relevant_article_ids_by_query: Mapping[str, Sequence[str]],
    *,
    ks: Sequence[int] = (1, 3, 5),
) -> Dict[str, Any]:
    normalized_ks = tuple(sorted({int(k) for k in ks if int(k) > 0}))
    per_query: List[Dict[str, Any]] = []

    for query_id, relevant_article_ids in relevant_article_ids_by_query.items():
        ranked_article_ids = list(ranked_article_ids_by_query.get(query_id, ()))
        relevant_ids = [article_id for article_id in relevant_article_ids if article_id]
        relevant_set = set(relevant_ids)
        first_relevant_rank = next(
            (
                index
                for index, article_id in enumerate(ranked_article_ids, start=1)
                if article_id in relevant_set
            ),
            None,
        )
        query_metrics: Dict[str, Any] = {
            "query_id": query_id,
            "ranked_article_ids": ranked_article_ids,
            "relevant_article_ids": relevant_ids,
            "first_relevant_rank": first_relevant_rank,
            "reciprocal_rank": 0.0 if first_relevant_rank is None else 1.0 / first_relevant_rank,
            "hit_at_k": {},
            "recall_at_k": {},
        }

        for k in normalized_ks:
            top_k = ranked_article_ids[:k]
            matched = len(relevant_set.intersection(top_k))
            query_metrics["hit_at_k"][k] = 1.0 if matched else 0.0
            query_metrics["recall_at_k"][k] = 0.0 if not relevant_set else matched / len(relevant_set)

        per_query.append(query_metrics)

    query_count = len(per_query)
    if query_count == 0:
        return {
            "query_count": 0,
            "per_query": [],
            "hit_at_k": {k: 0.0 for k in normalized_ks},
            "recall_at_k": {k: 0.0 for k in normalized_ks},
            "mrr": 0.0,
        }

    return {
        "query_count": query_count,
        "per_query": per_query,
        "hit_at_k": {
            k: sum(item["hit_at_k"][k] for item in per_query) / query_count
            for k in normalized_ks
        },
        "recall_at_k": {
            k: sum(item["recall_at_k"][k] for item in per_query) / query_count
            for k in normalized_ks
        },
        "mrr": sum(item["reciprocal_rank"] for item in per_query) / query_count,
    }
