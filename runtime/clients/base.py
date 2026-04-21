# -*- coding: utf-8 -*-
"""
AIClient 抽象基类 — 所有 AI 后端均实现此接口
"""

from abc import ABC, abstractmethod


class AIClient(ABC):
    """统一的 AI 后端接口，所有 Product 通过此接口调用 AI，不感知具体后端。"""

    @abstractmethod
    def chat(self, prompt: str) -> str:
        """发送 prompt，返回纯文本响应。"""
        ...
