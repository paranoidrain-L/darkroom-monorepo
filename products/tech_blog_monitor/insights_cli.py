# -*- coding: utf-8 -*-
"""Tech Blog Monitor - Phase 6 insights CLI。"""

from __future__ import annotations

import argparse
import sys

from products.tech_blog_monitor.insights import (
    InsightQuery,
    analyze_insights,
    format_insight_report,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Tech Blog Monitor Insights")
    parser.add_argument("--db", required=True, help="sqlite 资产库路径")
    parser.add_argument("--days", type=int, default=14, help="分析窗口天数")
    parser.add_argument("--top-k", type=int, default=5, help="主题 / 热点输出上限")
    parser.add_argument("--max-articles", type=int, default=1000, help="最多读取文章数")
    args = parser.parse_args()

    try:
        report = analyze_insights(
            args.db,
            InsightQuery(
                days=args.days,
                top_k=args.top_k,
                max_articles=args.max_articles,
            ),
        )
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)

    print(format_insight_report(report))
    sys.exit(0)


if __name__ == "__main__":
    main()
