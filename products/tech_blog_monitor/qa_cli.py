# -*- coding: utf-8 -*-
"""Tech Blog Monitor - Phase 5 QA CLI。"""

from __future__ import annotations

import argparse
import sys

from products.tech_blog_monitor.qa import answer_question, format_qa_result
from products.tech_blog_monitor.retrieval import RetrievalQuery


def main() -> None:
    parser = argparse.ArgumentParser(description="Tech Blog Monitor QA")
    parser.add_argument("--db", required=True, help="sqlite 资产库路径")
    parser.add_argument("--question", required=True, help="要回答的问题")
    parser.add_argument("--limit", type=int, default=3, help="最多引用几篇文章")
    parser.add_argument("--candidate-limit", type=int, default=25, help="候选 chunk 数")
    args = parser.parse_args()

    try:
        result = answer_question(
            args.db,
            RetrievalQuery(
                question=args.question,
                limit=args.limit,
                candidate_limit=args.candidate_limit,
            ),
        )
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)

    print(format_qa_result(result))
    sys.exit(0 if result.status == "answered" else 2)


if __name__ == "__main__":
    main()
