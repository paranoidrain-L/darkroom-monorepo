# -*- coding: utf-8 -*-
"""
Tech Blog Monitor — Agent Entry Point

用法:
    # 单次执行
    PYTHONPATH=. python -m products.tech_blog_monitor.agent

    # 指定输出路径
    PYTHONPATH=. python -m products.tech_blog_monitor.agent --output report.md

    # 启动定时服务
    PYTHONPATH=. python -m products.tech_blog_monitor.agent serve
    PYTHONPATH=. python -m products.tech_blog_monitor.agent serve --times 09:00 18:00 --run-now

环境变量:
    TECH_BLOG_OUTPUT      报告输出路径（单次执行）
    TECH_BLOG_MAX_ARTICLES  每个 feed 最多抓取文章数（默认 5）
    AGENT_RUNTIME         AI 后端（默认 claude）
"""

import json
import sys


def _normalize_argv(argv: list[str]) -> list[str]:
    """允许无子命令直接传 run 参数，例如 `--output report.md`。"""
    if not argv:
        return argv
    if argv[0] in {"run", "serve", "feedback", "task", "ops", "-h", "--help"}:
        return argv
    return ["run", *argv]


def main() -> None:
    import argparse

    from products.tech_blog_monitor.config import TechBlogMonitorConfig
    from products.tech_blog_monitor.ops import build_operational_summary
    from products.tech_blog_monitor.tasks import LocalTaskRunner

    parser = argparse.ArgumentParser(description="Tech Blog Monitor Agent")
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="单次执行（默认）")
    run_parser.add_argument("--output", default=None, help="报告输出路径")
    run_parser.add_argument("--max-articles", type=int, default=None, help="每个 feed 最多抓取文章数")

    serve_parser = subparsers.add_parser("serve", help="启动定时监控服务")
    serve_parser.add_argument("--times", nargs="+", default=None, metavar="HH:MM")
    serve_parser.add_argument("--output-dir", default=None, metavar="DIR")
    serve_parser.add_argument("--run-now", action="store_true")

    feedback_parser = subparsers.add_parser("feedback", help="记录或查看反馈")
    feedback_subparsers = feedback_parser.add_subparsers(dest="feedback_command", required=True)
    feedback_add_parser = feedback_subparsers.add_parser("add", help="新增反馈")
    feedback_add_parser.add_argument("--db", required=True)
    feedback_add_parser.add_argument("--run-id", required=True)
    feedback_add_parser.add_argument("--role", required=True)
    feedback_add_parser.add_argument("--type", required=True)
    feedback_add_parser.add_argument("--text", default="")
    feedback_add_parser.add_argument("--metadata", default="{}")
    feedback_list_parser = feedback_subparsers.add_parser("list", help="查看反馈")
    feedback_list_parser.add_argument("--db", required=True)
    feedback_list_parser.add_argument("--run-id", default="")
    feedback_list_parser.add_argument("--role", default="")

    task_parser = subparsers.add_parser("task", help="执行标准化运维任务")
    task_subparsers = task_parser.add_subparsers(dest="task_command", required=True)
    rebuild_search_parser = task_subparsers.add_parser("rebuild-search-index", help="重建搜索索引")
    rebuild_search_parser.add_argument("--db", default="", help="sqlite 资产库路径")
    rebuild_search_parser.add_argument("--database-url", default="", help="数据库 URL")
    rebuild_search_parser.add_argument("--requested-by", default="cli", help="任务发起方")
    rebuild_retrieval_parser = task_subparsers.add_parser(
        "rebuild-retrieval-index",
        help="重建检索索引",
    )
    rebuild_retrieval_parser.add_argument("--db", default="", help="sqlite 资产库路径")
    rebuild_retrieval_parser.add_argument("--database-url", default="", help="数据库 URL")
    rebuild_retrieval_parser.add_argument("--requested-by", default="cli", help="任务发起方")

    ops_parser = subparsers.add_parser("ops", help="查看运行健康汇总")
    ops_subparsers = ops_parser.add_subparsers(dest="ops_command", required=True)
    ops_summary_parser = ops_subparsers.add_parser("summary", help="输出最小运营看板汇总")
    ops_summary_parser.add_argument("--db", default="", help="sqlite 资产库路径")
    ops_summary_parser.add_argument("--database-url", default="", help="数据库 URL")
    ops_summary_parser.add_argument("--limit", type=int, default=50, help="聚合最近任务数")

    args = parser.parse_args(_normalize_argv(sys.argv[1:]))

    if args.command == "feedback":
        from products.tech_blog_monitor.feedback_cli import main as feedback_main

        feedback_main()
        return

    config = TechBlogMonitorConfig.from_env()

    if args.command == "task":
        runner = LocalTaskRunner(config)
        if args.task_command == "rebuild-search-index":
            result = runner.rebuild_search_index(
                asset_db_path=args.db,
                database_url=args.database_url,
                requested_by=args.requested_by,
                trigger_source="cli",
            )
        else:
            result = runner.rebuild_retrieval_index(
                asset_db_path=args.db,
                database_url=args.database_url,
                requested_by=args.requested_by,
                trigger_source="cli",
            )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.command == "ops":
        asset_db_path = args.db or config.asset_db_path
        database_url = args.database_url or config.database_url
        result = build_operational_summary(
            asset_db_path,
            database_url=database_url,
            limit=args.limit,
        ).to_dict()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.command == "serve":
        from products.tech_blog_monitor.scheduler import _DEFAULT_OUTPUT_DIR, _job, start

        output_dir = args.output_dir or _DEFAULT_OUTPUT_DIR
        times = args.times or ["09:00"]
        if args.run_now:
            _job(output_dir)
        start(times, output_dir)
        return

    # 单次执行（run 或无子命令）
    if hasattr(args, "output") and args.output:
        config.output_path = args.output
    if hasattr(args, "max_articles") and args.max_articles:
        config.max_articles_per_feed = args.max_articles

    runner = LocalTaskRunner(config)
    sys.exit(
        runner.run_monitor(
            config,
            task_type="manual_run",
            trigger_source="cli",
            requested_by="cli",
        )
    )


if __name__ == "__main__":
    main()
