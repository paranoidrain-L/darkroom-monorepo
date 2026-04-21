"""RSS source adapter."""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

import requests

if TYPE_CHECKING:
    from products.tech_blog_monitor.config import FeedSource
    from products.tech_blog_monitor.fetcher import Article, FeedHealth


class RssSourceAdapter:
    def __init__(
        self,
        fetch_rss_source: Callable[
            ["FeedSource"],
            tuple[list["Article"], "FeedHealth"],
        ],
    ) -> None:
        self._fetch_rss_source = fetch_rss_source

    @property
    def source_type(self) -> str:
        return "rss"

    def fetch(
        self,
        source: "FeedSource",
        *,
        max_articles: int,
        session: requests.Session | None = None,
    ) -> tuple[list["Article"], "FeedHealth"]:
        return self._fetch_rss_source(
            source,
            max_articles=max_articles,
            session=session,
        )
