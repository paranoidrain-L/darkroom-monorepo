# -*- coding: utf-8 -*-
"""Content extractor result types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ExtractionResult:
    clean_text: str
    source: str
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
