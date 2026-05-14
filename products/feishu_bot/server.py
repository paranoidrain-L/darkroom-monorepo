# -*- coding: utf-8 -*-
"""Deprecated webhook entrypoint."""

from __future__ import annotations

from loguru import logger


class WebhookServer:
    """Webhook mode has been removed from this package."""

    def __init__(self, *args, **kwargs) -> None:
        raise RuntimeError("Webhook 模式已移除，请改用 `python -m products.feishu_bot.client`。")


def main() -> None:
    logger.error("Webhook 模式已移除，请改用 `python -m products.feishu_bot.client`。")


if __name__ == "__main__":
    main()
