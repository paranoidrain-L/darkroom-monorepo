"""Tech Blog Monitor minimal FastAPI app。"""

from __future__ import annotations

import time
from dataclasses import asdict
from typing import Any

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

from products.tech_blog_monitor.api.deps import get_asset_db_path, get_config, get_repository_bundle
from products.tech_blog_monitor.api.schemas import (
    ArticleResponse,
    ArticlesResponse,
    FeedbackRequest,
    FeedbackResponse,
    HealthResponse,
    InsightReportResponse,
    OperationalSummaryResponse,
    RunDetailResponse,
    RunsResponse,
    SearchResponse,
)
from products.tech_blog_monitor.config import TechBlogMonitorConfig
from products.tech_blog_monitor.feedback import record_feedback
from products.tech_blog_monitor.insights import InsightQuery, InsightReport, analyze_insights
from products.tech_blog_monitor.ops import build_operational_summary
from products.tech_blog_monitor.repository_provider import RepositoryBundle
from products.tech_blog_monitor.search import SearchQuery, search_articles

app = FastAPI(title="Tech Blog Monitor API", version="0.1.0")


@app.exception_handler(FileNotFoundError)
async def handle_file_not_found(_, exc: FileNotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(ValueError)
async def handle_value_error(_, exc: ValueError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


def _serialize_insight_report(report: InsightReport) -> dict[str, Any]:
    return {
        "status": report.status,
        "summary": report.summary,
        "topic_clusters": [asdict(item) for item in report.topic_clusters],
        "source_comparisons": [asdict(item) for item in report.source_comparisons],
        "timeline": [asdict(item) for item in report.timeline],
        "hot_signals": [asdict(item) for item in report.hot_signals],
    }


@app.get("/health", response_model=HealthResponse)
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/runs", response_model=RunsResponse)
async def list_runs(
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    bundle: RepositoryBundle = Depends(get_repository_bundle),
) -> dict[str, list[dict[str, Any]]]:
    return {"items": bundle.run_repository.list_runs(limit=limit, offset=offset)}


@app.get("/runs/{run_id}", response_model=RunDetailResponse)
async def get_run_detail(
    run_id: str,
    bundle: RepositoryBundle = Depends(get_repository_bundle),
) -> dict[str, Any]:
    run = bundle.run_repository.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"run not found: {run_id}")
    return {
        "run": run,
        "articles": bundle.run_repository.list_run_articles(run_id),
    }


@app.get("/articles", response_model=ArticlesResponse)
async def list_articles(
    source_name: str = "",
    category: str = "",
    limit: int = Query(default=20, ge=1, le=200),
    bundle: RepositoryBundle = Depends(get_repository_bundle),
) -> dict[str, list[dict[str, Any]]]:
    return {
        "items": bundle.article_repository.list_articles(
            source_name=source_name or None,
            category=category or None,
            limit=limit,
        )
    }


@app.get("/articles/{article_id}", response_model=ArticleResponse)
async def get_article(
    article_id: str,
    bundle: RepositoryBundle = Depends(get_repository_bundle),
) -> dict[str, dict[str, Any]]:
    article = bundle.article_repository.get_article(article_id)
    if article is None:
        raise HTTPException(status_code=404, detail=f"article not found: {article_id}")
    return {"article": article}


@app.get("/search", response_model=SearchResponse)
async def search(
    query: str = "",
    source_name: str = "",
    category: str = "",
    topic: str = "",
    tag: str = "",
    days: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=200),
    asset_db_path: str = Depends(get_asset_db_path),
    config: TechBlogMonitorConfig = Depends(get_config),
) -> dict[str, list[dict[str, Any]]]:
    results = search_articles(
        asset_db_path,
        SearchQuery(
            query=query,
            source_name=source_name,
            category=category,
            topic=topic,
            tag=tag,
            days=days,
            limit=limit,
        ),
        database_url=config.database_url.strip(),
    )
    return {"items": results}


@app.get("/insights", response_model=InsightReportResponse)
async def insights(
    days: int = Query(default=14, ge=1, le=365),
    top_k: int = Query(default=5, ge=1, le=50),
    max_articles: int = Query(default=1000, ge=1, le=5000),
    asset_db_path: str = Depends(get_asset_db_path),
    config: TechBlogMonitorConfig = Depends(get_config),
) -> dict[str, Any]:
    report = analyze_insights(
        asset_db_path,
        InsightQuery(days=days, top_k=top_k, max_articles=max_articles),
        database_url=config.database_url.strip(),
    )
    return _serialize_insight_report(report)


@app.get("/ops/summary", response_model=OperationalSummaryResponse)
async def ops_summary(
    limit: int = Query(default=50, ge=1, le=500),
    asset_db_path: str = Depends(get_asset_db_path),
    config: TechBlogMonitorConfig = Depends(get_config),
) -> dict[str, Any]:
    return build_operational_summary(
        asset_db_path,
        database_url=config.database_url.strip(),
        limit=limit,
    ).to_dict()


@app.post("/feedback", response_model=FeedbackResponse, status_code=201)
async def add_feedback(
    request: FeedbackRequest,
    asset_db_path: str = Depends(get_asset_db_path),
    config: TechBlogMonitorConfig = Depends(get_config),
) -> dict[str, str]:
    feedback_id = record_feedback(
        asset_db_path,
        run_id=request.run_id,
        role=request.role,
        feedback_type=request.feedback_type,
        feedback_text=request.feedback_text,
        metadata=request.metadata,
        created_at=request.created_at or int(time.time()),
        database_url=config.database_url.strip(),
    )
    return {"feedback_id": feedback_id}


def main() -> None:
    uvicorn.run("products.tech_blog_monitor.api.app:app", host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
