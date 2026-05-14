# -*- coding: utf-8 -*-
"""Prompt and memory behavior policy."""

from __future__ import annotations

from dataclasses import dataclass

from runtime.memory.types import MemoryMode


@dataclass(frozen=True)
class MemoryPolicy:
    """Controls prompt composition and long-term memory usage."""

    mode: MemoryMode = MemoryMode.ON
    recent_turn_limit: int = 8
    facts_limit: int = 5
    max_prompt_chars: int = 16000
    max_turn_chars: int = 4000
    max_summary_chars: int = 3000
    max_fact_chars: int = 1000
    summary_after_turns: int = 12
    summary_refresh_turns: int = 6
    enable_fact_extraction: bool = False
    enable_sensitive_filter: bool = True

    @property
    def memory_enabled(self) -> bool:
        return self.mode == MemoryMode.ON

    def for_mode(self, mode: MemoryMode) -> "MemoryPolicy":
        return MemoryPolicy(
            mode=mode,
            recent_turn_limit=self.recent_turn_limit,
            facts_limit=self.facts_limit,
            max_prompt_chars=self.max_prompt_chars,
            max_turn_chars=self.max_turn_chars,
            max_summary_chars=self.max_summary_chars,
            max_fact_chars=self.max_fact_chars,
            summary_after_turns=self.summary_after_turns,
            summary_refresh_turns=self.summary_refresh_turns,
            enable_fact_extraction=self.enable_fact_extraction,
            enable_sensitive_filter=self.enable_sensitive_filter,
        )

    @staticmethod
    def truncate_text(text: str, max_chars: int) -> str:
        if max_chars <= 0:
            return ""
        if len(text) <= max_chars:
            return text
        marker = "\n... (truncated)"
        keep = max(max_chars - len(marker), 0)
        return text[:keep] + marker


DEFAULT_MEMORY_POLICY = MemoryPolicy()
