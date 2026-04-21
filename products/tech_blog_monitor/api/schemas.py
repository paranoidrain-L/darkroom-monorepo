"""Tech Blog Monitor API schemas。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str


class RunsResponse(BaseModel):
    items: list[dict[str, Any]]


class RunDetailResponse(BaseModel):
    run: dict[str, Any]
    articles: list[dict[str, Any]]


class ArticlesResponse(BaseModel):
    items: list[dict[str, Any]]


class ArticleResponse(BaseModel):
    article: dict[str, Any]


class SearchResponse(BaseModel):
    items: list[dict[str, Any]]


class TopicClusterResponse(BaseModel):
    topic: str
    article_count: int
    source_count: int
    representative_titles: list[str]
    trend_label: str
    delta: int


class SourceComparisonResponse(BaseModel):
    source_name: str
    article_count: int
    dominant_topics: list[str]
    unique_topic_count: int


class TimelinePointResponse(BaseModel):
    date: str
    article_count: int
    top_topic: str


class HotSignalResponse(BaseModel):
    topic: str
    score: float
    reason: str


class InsightReportResponse(BaseModel):
    status: str
    summary: str
    topic_clusters: list[TopicClusterResponse]
    source_comparisons: list[SourceComparisonResponse]
    timeline: list[TimelinePointResponse]
    hot_signals: list[HotSignalResponse]


class FeedbackRequest(BaseModel):
    run_id: str
    role: str
    feedback_type: str
    feedback_text: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: int | None = None


class FeedbackResponse(BaseModel):
    feedback_id: str


class OperationalKPIResponse(BaseModel):
    name: str
    value: float | None
    numerator: int
    denominator: int
    unit: str


class FailureSampleResponse(BaseModel):
    task_id: str
    task_type: str
    task_status: str
    started_at: int
    error_code: str
    error_message: str


class OperationalSummaryResponse(BaseModel):
    window_size: int
    task_status_counts: dict[str, int]
    task_type_counts: dict[str, int]
    kpis: list[OperationalKPIResponse]
    recent_failures: list[FailureSampleResponse]
    latest_task_id: str
    latest_run_task_id: str
