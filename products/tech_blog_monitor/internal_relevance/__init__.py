"""Internal relevance public entrypoints."""

from products.tech_blog_monitor.internal_relevance.manifest_scanner import scan_repo_roots
from products.tech_blog_monitor.internal_relevance.models import (
    ManifestScanResult,
    RelevanceReport,
    StackProfile,
    StackSignal,
)
from products.tech_blog_monitor.internal_relevance.profile_loader import load_stack_profile
from products.tech_blog_monitor.internal_relevance.report import build_markdown_summary
from products.tech_blog_monitor.internal_relevance.scorer import evaluate_internal_relevance

__all__ = [
    "ManifestScanResult",
    "RelevanceReport",
    "StackProfile",
    "StackSignal",
    "build_markdown_summary",
    "evaluate_internal_relevance",
    "load_stack_profile",
    "scan_repo_roots",
]
