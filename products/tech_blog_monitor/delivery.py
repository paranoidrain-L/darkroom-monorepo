# -*- coding: utf-8 -*-
"""Tech Blog Monitor - Phase 7 分发链路。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

import requests

from products.tech_blog_monitor.archive_store import ArchiveStore
from products.tech_blog_monitor.fetcher import Article
from products.tech_blog_monitor.insights import InsightReport
from products.tech_blog_monitor.observability import RunContext

_CST = timezone(timedelta(hours=8))
_ALLOWED_ROLES = {"executive", "engineer", "researcher"}


@dataclass
class DeliveryRequest:
    run_id: str
    generated_at: int
    cadence: str
    webhook_url: str
    roles: List[str]
    max_retries: int = 3
    rate_limit_per_minute: int = 3


def build_role_digest(
    *,
    role: str,
    report_markdown: str,
    articles: Sequence[Article],
    insight_report: Optional[InsightReport],
    generated_at: int,
    cadence: str,
) -> Dict[str, object]:
    if role not in _ALLOWED_ROLES:
        raise ValueError(f"不支持的角色: {role}")

    generated_dt = datetime.fromtimestamp(generated_at, tz=_CST)
    top_articles = list(articles[:5])
    lines = [
        f"Tech Blog {cadence} digest",
        f"生成时间: {generated_dt.strftime('%Y-%m-%d %H:%M')} CST",
    ]

    if role == "executive":
        lines.append("视角: 管理层摘要")
        if insight_report:
            lines.append(insight_report.summary)
            for signal in insight_report.hot_signals[:3]:
                lines.append(f"- 热点: {signal.topic} ({signal.reason})")
        else:
            lines.append(f"本期共 {len(articles)} 篇文章。")
    elif role == "engineer":
        lines.append("视角: 工程关注")
        for article in top_articles:
            topic = article.topic or article.category
            summary = article.one_line_summary or article.ai_summary or article.rss_summary[:120]
            lines.append(f"- [{topic}] {article.title}: {summary}")
    else:
        lines.append("视角: 研究观察")
        if insight_report and insight_report.topic_clusters:
            for cluster in insight_report.topic_clusters[:3]:
                titles = " | ".join(cluster.representative_titles[:2])
                lines.append(
                    f"- {cluster.topic}: trend={cluster.trend_label}, delta={cluster.delta}, {titles}"
                )
        else:
            for article in top_articles:
                lines.append(f"- {article.title}")

    return {
        "role": role,
        "cadence": cadence,
        "title": f"Tech Blog {role} digest",
        "text": "\n".join(lines),
        "article_urls": [article.url for article in top_articles],
        "report_preview": report_markdown[:500],
    }


def _default_sender(url: str, payload: Dict[str, object]) -> tuple[int, str]:
    response = requests.post(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        timeout=10,
    )
    return response.status_code, response.text


def _build_dedupe_key(run_id: str, role: str, cadence: str) -> str:
    return f"{run_id}:{role}:{cadence}"


def enqueue_deliveries(
    *,
    store: ArchiveStore,
    request: DeliveryRequest,
    report_markdown: str,
    articles: Sequence[Article],
    insight_report: Optional[InsightReport],
) -> List[Dict[str, object]]:
    deliveries: List[Dict[str, object]] = []
    for role in request.roles:
        payload = build_role_digest(
            role=role,
            report_markdown=report_markdown,
            articles=articles,
            insight_report=insight_report,
            generated_at=request.generated_at,
            cadence=request.cadence,
        )
        delivery = store.create_delivery(
            run_id=request.run_id,
            role=role,
            cadence=request.cadence,
            dedupe_key=_build_dedupe_key(request.run_id, role, request.cadence),
            payload=payload,
            created_at=request.generated_at,
        )
        deliveries.append(delivery)
    return deliveries


def dispatch_pending_deliveries(
    *,
    store: ArchiveStore,
    request: DeliveryRequest,
    sender: Callable[[str, Dict[str, object]], tuple[int, str]] | None = None,
    now_ts: Optional[int] = None,
    run_context: RunContext | None = None,
) -> List[Dict[str, object]]:
    sender = sender or _default_sender
    now_ts = now_ts or request.generated_at
    recent_window_start = now_ts - 60
    sent_recently = [
        item
        for item in store.list_deliveries(status="delivered")
        if isinstance(item.get("delivered_at"), int) and item["delivered_at"] >= recent_window_start
    ]
    rate_budget = max(request.rate_limit_per_minute - len(sent_recently), 0)
    processed: List[Dict[str, object]] = []

    for delivery in store.list_deliveries(run_id=request.run_id):
        task = None
        if run_context is not None:
            task = run_context.start_task(
                task_id=f"{run_context.run_id}:delivery:{delivery['delivery_id']}",
                task_type="dispatch_delivery",
                dimensions={
                    "delivery_id": delivery["delivery_id"],
                    "role": delivery["role"],
                    "cadence": delivery["cadence"],
                },
            )

        if delivery["status"] == "delivered":
            processed.append(delivery)
            if task is not None:
                task.complete(
                    status="success",
                    dimensions={
                        "status": "delivered",
                        "attempt_count": delivery["attempt_count"],
                    },
                )
            continue

        if delivery["attempt_count"] >= request.max_retries:
            store.mark_delivery_attempt(
                delivery["delivery_id"],
                status="failed",
                error="max retries exceeded",
                delivered_at=None,
                updated_at=now_ts,
            )
            updated = next(
                item
                for item in store.list_deliveries(run_id=request.run_id)
                if item["delivery_id"] == delivery["delivery_id"]
            )
            processed.append(updated)
            if task is not None:
                task.complete(
                    status="failed",
                    error_message="max retries exceeded",
                    dimensions={
                        "status": updated["status"],
                        "attempt_count": updated["attempt_count"],
                    },
                )
            continue

        if rate_budget <= 0:
            store.mark_delivery_attempt(
                delivery["delivery_id"],
                status="rate_limited",
                error="rate limit exceeded",
                delivered_at=None,
                updated_at=now_ts,
            )
            updated = next(
                item
                for item in store.list_deliveries(run_id=request.run_id)
                if item["delivery_id"] == delivery["delivery_id"]
            )
            processed.append(updated)
            if task is not None:
                task.complete(
                    status="failed",
                    error_message="rate limit exceeded",
                    dimensions={
                        "status": updated["status"],
                        "attempt_count": updated["attempt_count"],
                    },
                )
            continue

        try:
            status_code, body = sender(request.webhook_url, delivery["payload"])
            if 200 <= status_code < 300:
                store.mark_delivery_attempt(
                    delivery["delivery_id"],
                    status="delivered",
                    error="",
                    delivered_at=now_ts,
                    updated_at=now_ts,
                )
                rate_budget -= 1
                task_status = "success"
                task_error = ""
            else:
                new_status = "pending" if delivery["attempt_count"] + 1 < request.max_retries else "failed"
                store.mark_delivery_attempt(
                    delivery["delivery_id"],
                    status=new_status,
                    error=f"http {status_code}: {body[:200]}",
                    delivered_at=None,
                    updated_at=now_ts,
                )
                task_status = "failed"
                task_error = f"http {status_code}: {body[:200]}"
        except Exception as exc:
            new_status = "pending" if delivery["attempt_count"] + 1 < request.max_retries else "failed"
            store.mark_delivery_attempt(
                delivery["delivery_id"],
                status=new_status,
                error=f"sender exception: {exc}",
                delivered_at=None,
                updated_at=now_ts,
            )
            task_status = "failed"
            task_error = f"sender exception: {exc}"

        updated = next(
            item
            for item in store.list_deliveries(run_id=request.run_id)
            if item["delivery_id"] == delivery["delivery_id"]
        )
        processed.append(updated)
        if task is not None:
            task.complete(
                status=task_status,
                error_message=task_error,
                dimensions={
                    "status": updated["status"],
                    "attempt_count": updated["attempt_count"],
                },
            )

    return processed


def maybe_dispatch_deliveries(
    *,
    db_path: str,
    request: DeliveryRequest,
    report_markdown: str,
    articles: Sequence[Article],
    insight_report: Optional[InsightReport],
    sender: Callable[[str, Dict[str, object]], tuple[int, str]] | None = None,
    now_ts: Optional[int] = None,
    run_context: RunContext | None = None,
) -> List[Dict[str, object]]:
    if not Path(db_path).exists():
        raise FileNotFoundError(f"资产库不存在: {db_path}")

    with ArchiveStore(db_path) as store:
        enqueue_deliveries(
            store=store,
            request=request,
            report_markdown=report_markdown,
            articles=articles,
            insight_report=insight_report,
        )
        return dispatch_pending_deliveries(
            store=store,
            request=request,
            sender=sender,
            now_ts=now_ts,
            run_context=run_context,
        )
