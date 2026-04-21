# -*- coding: utf-8 -*-
"""Structured observability event models for tech_blog_monitor."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class StageEvent:
    run_id: str
    task_id: str
    task_type: str
    stage_name: str
    event_type: str
    observed_at: str
    dimensions: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StageOutcome:
    run_id: str
    task_id: str
    task_type: str
    stage_name: str
    started_at: str
    finished_at: str
    duration_ms: int
    status: str
    error_code: str = ""
    error_message: str = ""
    dimensions: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TaskResult:
    run_id: str
    task_id: str
    task_type: str
    started_at: str
    finished_at: str
    duration_ms: int
    status: str
    error_code: str = ""
    error_message: str = ""
    dimensions: dict[str, Any] = field(default_factory=dict)
