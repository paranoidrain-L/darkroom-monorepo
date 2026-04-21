"""Helpers for rendering internal relevance summaries."""

from __future__ import annotations

from products.tech_blog_monitor.internal_relevance.models import RelevanceReport


def build_markdown_summary(report: RelevanceReport) -> list[str]:
    lines = ["## Internal Relevance", ""]
    if report.status == "skipped":
        lines.extend([report.summary, ""])
        return lines

    lines.append(report.summary)
    lines.append("")
    lines.append(
        "level counts: "
        + ", ".join(f"{level}={count}" for level, count in sorted(report.level_counts.items()))
    )
    if report.top_matches:
        lines.append("")
        lines.append("top matches:")
        for item in report.top_matches:
            lines.append(
                f"- {item['title']} [{item['relevance_level']}] "
                f"score={item['relevance_score']:.2f} "
                f"signals={', '.join(item['matched_signal_names'])}"
            )
    if report.warnings:
        lines.append("")
        lines.append("warnings:")
        for warning in report.warnings:
            lines.append(f"- {warning}")
    lines.append("")
    return lines
