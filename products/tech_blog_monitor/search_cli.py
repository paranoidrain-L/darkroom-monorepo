# -*- coding: utf-8 -*-
"""Tech Blog Monitor — Phase 4 检索 CLI。"""

from __future__ import annotations

import argparse
import sys

from products.tech_blog_monitor.search import SearchQuery, format_search_results, search_articles


def main() -> None:
    parser = argparse.ArgumentParser(description="Tech Blog Monitor Search")
    parser.add_argument("--db", required=True, help="sqlite 资产库路径")
    parser.add_argument("--query", default="", help="关键词查询")
    parser.add_argument("--source", default="", help="来源过滤")
    parser.add_argument("--category", default="", help="分类过滤")
    parser.add_argument("--topic", default="", help="主题过滤")
    parser.add_argument("--tag", default="", help="标签过滤")
    parser.add_argument("--days", type=int, default=0, help="最近 N 天")
    parser.add_argument("--limit", type=int, default=20, help="最多返回结果数")
    args = parser.parse_args()

    try:
        results = search_articles(
            args.db,
            SearchQuery(
                query=args.query,
                source_name=args.source,
                category=args.category,
                topic=args.topic,
                tag=args.tag,
                days=args.days,
                limit=args.limit,
            ),
        )
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)

    print(format_search_results(results))
    sys.exit(0)


if __name__ == "__main__":
    main()
