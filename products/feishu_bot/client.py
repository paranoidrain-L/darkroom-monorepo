# -*- coding: utf-8 -*-
"""CLI entrypoint for the lark-cli based Feishu bot."""

from __future__ import annotations

import argparse

from loguru import logger

from products.feishu_bot.bot import FeishuBot
from products.feishu_bot.config import FeishuBotConfig
from products.feishu_bot.lark_cli import LarkCLIError

FeishuBotLongConnection = FeishuBot


def main() -> None:
    parser = argparse.ArgumentParser(description="飞书机器人长连接模式（出站操作走 lark-cli）")
    parser.add_argument(
        "--config",
        type=str,
        default="config/feishu_config.json",
        help="配置文件路径",
    )
    args = parser.parse_args()

    config = FeishuBotConfig.from_json(args.config)
    if not config.validate():
        logger.error("配置验证失败，请检查环境变量或配置文件。")
        return

    try:
        bot = FeishuBot(config)
        bot.start()
    except LarkCLIError as exc:
        logger.error(f"lark-cli 初始化失败: {exc}")
    except Exception as exc:
        logger.exception(f"启动飞书机器人失败: {exc}")


if __name__ == "__main__":
    main()
