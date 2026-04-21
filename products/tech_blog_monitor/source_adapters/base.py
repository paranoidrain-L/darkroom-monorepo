"""Minimal source adapter protocol for fetch pipeline."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

import requests

if TYPE_CHECKING:
    from products.tech_blog_monitor.config import FeedSource
    from products.tech_blog_monitor.fetcher import Article, FeedHealth


class SourceAdapter(Protocol):
    @property
    def source_type(self) -> str:
        ...

    def fetch(
        self,
        source: "FeedSource",
        *,
        max_articles: int,
        session: requests.Session | None = None,
    ) -> tuple[list["Article"], "FeedHealth"]:
        ...
