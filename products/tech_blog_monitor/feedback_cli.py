# -*- coding: utf-8 -*-
"""Tech Blog Monitor - Phase 7 feedback CLI。"""

from __future__ import annotations

import argparse
import json
import sys
import time

from products.tech_blog_monitor.feedback import list_feedback, record_feedback


def main() -> None:
    parser = argparse.ArgumentParser(description="Tech Blog Monitor Feedback")
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_parser = subparsers.add_parser("add", help="写入反馈")
    add_parser.add_argument("--db", required=True)
    add_parser.add_argument("--run-id", required=True)
    add_parser.add_argument("--role", required=True)
    add_parser.add_argument("--type", required=True)
    add_parser.add_argument("--text", default="")
    add_parser.add_argument("--metadata", default="{}")

    list_parser = subparsers.add_parser("list", help="查看反馈")
    list_parser.add_argument("--db", required=True)
    list_parser.add_argument("--run-id", default="")
    list_parser.add_argument("--role", default="")

    args = parser.parse_args()

    try:
        if args.command == "add":
            metadata = json.loads(args.metadata)
            feedback_id = record_feedback(
                args.db,
                run_id=args.run_id,
                role=args.role,
                feedback_type=args.type,
                feedback_text=args.text,
                metadata=metadata,
                created_at=int(time.time()),
            )
            print(feedback_id)
            sys.exit(0)

        items = list_feedback(
            args.db,
            run_id=args.run_id,
            role=args.role,
        )
        print(json.dumps(items, ensure_ascii=False, indent=2))
        sys.exit(0)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
