"""Source adapter contracts and built-in adapters."""

from products.tech_blog_monitor.source_adapters.base import SourceAdapter
from products.tech_blog_monitor.source_adapters.changelog_adapter import ChangelogAdapter
from products.tech_blog_monitor.source_adapters.github_releases_adapter import (
    GitHubReleasesAdapter,
)
from products.tech_blog_monitor.source_adapters.rss_adapter import RssSourceAdapter

__all__ = [
    "ChangelogAdapter",
    "GitHubReleasesAdapter",
    "RssSourceAdapter",
    "SourceAdapter",
]
