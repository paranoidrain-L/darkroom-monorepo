"""Data models for internal relevance evaluation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class StackSignal:
    signal_id: str
    name: str
    kind: str
    aliases: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    weight: float = 1.0
    source: str = ""
    source_detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class StackProfile:
    signals: list[StackSignal] = field(default_factory=list)
    source_priorities: dict[str, float] = field(default_factory=dict)
    profile_name: str = ""
    loaded_from: str = ""
    warnings: list[str] = field(default_factory=list)

    def dependency_signals(self) -> list[StackSignal]:
        return [signal for signal in self.signals if signal.kind == "dependency"]

    def topic_signals(self) -> list[StackSignal]:
        return [signal for signal in self.signals if signal.kind == "topic"]


@dataclass
class ManifestScanResult:
    signals: list[StackSignal] = field(default_factory=list)
    scanned_files: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class RelevanceReport:
    status: str
    summary: str
    signal_count: int
    dependency_signal_count: int
    topic_signal_count: int
    scanned_repo_roots: list[str] = field(default_factory=list)
    scanned_manifest_count: int = 0
    article_count: int = 0
    matched_article_count: int = 0
    level_counts: dict[str, int] = field(default_factory=dict)
    top_matches: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
