"""Structured changelog source adapter."""

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


class ChangelogAdapter:
    @property
    def source_type(self) -> str:
        return "changelog"

    def fetch(
        self,
        source,
        *,
        max_articles: int,
        session: requests.Session | None = None,
    ) -> tuple[list["Article"], "FeedHealth"]:
        from products.tech_blog_monitor.fetcher import FeedHealth

        if not source.enabled:
            return [], FeedHealth(
                name=source.name,
                url=source.url,
                success=False,
                error="disabled",
                source_type=source.source_type,
            )

        requester = session or requests
        headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json", **source.headers}
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

        try:
            if source.metadata.get("format") == "pypi":
                articles = self._parse_pypi_payload(
                    source,
                    payload,
                    fetch_ts=fetch_ts,
                    max_articles=max_articles,
                )
            else:
                articles = self._parse_generic_payload(
                    source,
                    payload,
                    fetch_ts=fetch_ts,
                    max_articles=max_articles,
                )
        except Exception as exc:
            return [], FeedHealth(
                name=source.name,
                url=source.url,
                success=False,
                error=str(exc),
                source_type=source.source_type,
            )

        return articles, FeedHealth(
            name=source.name,
            url=source.url,
            success=True,
            article_count=len(articles),
            source_type=source.source_type,
        )

    def _parse_generic_payload(
        self,
        source,
        payload,
        *,
        fetch_ts: int,
        max_articles: int,
    ) -> list[Article]:
        from products.tech_blog_monitor.fetcher import Article

        items_key = str(source.metadata.get("items_key") or "items")
        if isinstance(payload, list):
            items = payload
        elif isinstance(payload, dict):
            items = payload.get(items_key, [])
        else:
            items = []

        if not isinstance(items, list):
            raise ValueError("changelog payload must be a list or contain a list items_key")

        title_field = str(source.metadata.get("title_field") or "title")
        url_field = str(source.metadata.get("url_field") or "url")
        summary_field = str(source.metadata.get("summary_field") or "summary")
        published_field = str(source.metadata.get("published_field") or "published_at")

        articles: list[Article] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            title = str(item.get(title_field) or "").strip()
            url = str(item.get(url_field) or "").strip()
            if not title or not url:
                continue
            published = _parse_iso_datetime(item.get(published_field))
            published_ts = int(published.timestamp()) if published else None
            summary = _collapse_text(item.get(summary_field))
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
        return articles

    def _parse_pypi_payload(
        self,
        source,
        payload,
        *,
        fetch_ts: int,
        max_articles: int,
    ) -> list[Article]:
        from products.tech_blog_monitor.fetcher import Article

        if not isinstance(payload, dict):
            raise ValueError("pypi payload must be a dict")

        info = payload.get("info") or {}
        releases = payload.get("releases") or {}
        if not isinstance(info, dict) or not isinstance(releases, dict):
            raise ValueError("pypi payload missing info or releases")

        package_name = str(info.get("name") or source.name).strip()
        summary = _collapse_text(info.get("summary"))
        project_url = str(info.get("package_url") or source.url).rstrip("/")
        release_url_template = str(
            source.metadata.get("release_url_template")
            or f"{project_url}/{{version}}/"
        )

        articles: list[Article] = []
        for version, files in releases.items():
            if not isinstance(version, str) or not isinstance(files, list) or not files:
                continue

            published = None
            for file_item in files:
                if not isinstance(file_item, dict):
                    continue
                candidate = _parse_iso_datetime(file_item.get("upload_time_iso_8601"))
                if candidate is None:
                    continue
                if published is None or candidate > published:
                    published = candidate

            url = release_url_template.format(version=version)
            published_ts = int(published.timestamp()) if published else None
            articles.append(
                Article(
                    title=f"{package_name} {version}",
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

        articles.sort(
            key=lambda article: article.published or datetime.min.replace(tzinfo=_UTC),
            reverse=True,
        )
        return articles[: max_articles] if max_articles > 0 else articles
