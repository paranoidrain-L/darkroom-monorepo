"""GitHub releases source adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

import requests

if TYPE_CHECKING:
    from products.tech_blog_monitor.fetcher import Article, FeedHealth

_UTC = timezone.utc


def _parse_iso_datetime(raw: str | None) -> datetime | None:
    if not raw or not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(_UTC)
    except ValueError:
        return None


def _collapse_text(raw: str | None, *, limit: int = 500) -> str:
    if not raw:
        return ""
    return " ".join(str(raw).split())[:limit]


class GitHubReleasesAdapter:
    @property
    def source_type(self) -> str:
        return "github_releases"

    def fetch(
        self,
        source,
        *,
        max_articles: int,
        session: requests.Session | None = None,
    ) -> tuple[list["Article"], "FeedHealth"]:
        from products.tech_blog_monitor.fetcher import Article, FeedHealth

        if not source.enabled:
            return [], FeedHealth(
                name=source.name,
                url=source.url,
                success=False,
                error="disabled",
                source_type=source.source_type,
            )

        requester = session or requests
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/vnd.github+json",
            **source.headers,
        }
        fetch_ts = int(datetime.now(_UTC).timestamp())

        try:
            response = requester.get(
                source.url,
                timeout=source.timeout,
                headers=headers,
                verify=source.verify_ssl,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            return [], FeedHealth(
                name=source.name,
                url=source.url,
                success=False,
                error=str(exc),
                source_type=source.source_type,
            )

        if not isinstance(payload, list):
            return [], FeedHealth(
                name=source.name,
                url=source.url,
                success=False,
                error="github releases payload must be a list",
                source_type=source.source_type,
            )

        include_prereleases = bool(source.metadata.get("include_prereleases", False))
        articles: list[Article] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            if item.get("draft"):
                continue
            if not include_prereleases and item.get("prerelease"):
                continue

            url = str(item.get("html_url") or "").strip()
            tag_name = str(item.get("tag_name") or "").strip()
            title = str(item.get("name") or tag_name or "").strip()
            if not url or not title:
                continue

            published = _parse_iso_datetime(
                item.get("published_at") or item.get("created_at")
            )
            published_ts = int(published.timestamp()) if published else None
            summary = _collapse_text(item.get("body"))
            if not summary and tag_name:
                summary = f"Release {tag_name}"

            articles.append(
                Article(
                    title=title,
                    url=url,
                    source_name=source.name,
                    source_type=source.source_type,
                    category=source.category,
                    source_id=f"{source.name}::{url}",
                    rss_summary=summary,
                    published=published,
                    published_ts=published_ts,
                    fetched_at=fetch_ts,
                )
            )
            if 0 < max_articles <= len(articles):
                break

        return articles, FeedHealth(
            name=source.name,
            url=source.url,
            success=True,
            article_count=len(articles),
            source_type=source.source_type,
        )
