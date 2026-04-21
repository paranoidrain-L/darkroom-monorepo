# -*- coding: utf-8 -*-
"""
Tech Blog Monitor Scheduler — 持续运行的定时服务

兼容 facade：
- 旧导入路径 `products.tech_blog_monitor.scheduler` 继续可用
- 实际 APScheduler 本地路径已迁到 `local_scheduler.py`
"""

from __future__ import annotations

import argparse
import os

from products.tech_blog_monitor.local_scheduler import _DEFAULT_OUTPUT_DIR, _DEFAULT_TIMES
from products.tech_blog_monitor.local_scheduler import run_job as _job
from products.tech_blog_monitor.local_scheduler import start_local_scheduler as start


def main() -> None:
    parser = argparse.ArgumentParser(description="Tech Blog Monitor Scheduler")
    parser.add_argument("--times", nargs="+", default=None, metavar="HH:MM")
    parser.add_argument("--output-dir", default=None, metavar="DIR")
    parser.add_argument("--run-now", action="store_true")
    args = parser.parse_args()

    times_str = os.environ.get("TECH_BLOG_TIMES", "")
    times = args.times or (times_str.split(",") if times_str else _DEFAULT_TIMES)
    output_dir = args.output_dir or os.environ.get("TECH_BLOG_DIR", _DEFAULT_OUTPUT_DIR)

    if args.run_now:
        _job(output_dir)

    start(times, output_dir)


if __name__ == "__main__":
    main()
