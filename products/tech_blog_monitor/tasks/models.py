# -*- coding: utf-8 -*-
"""Task contracts for P2.3."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any


def build_task_idempotency_key(
    *,
    task_type: str,
    trigger_source: str,
    scope: str,
    input_payload: dict[str, Any],
) -> str:
    raw = json.dumps(
        {
            "task_type": task_type,
            "trigger_source": trigger_source,
            "scope": scope,
            "input_payload": input_payload,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    digest = sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"{task_type}:{digest}"


@dataclass(frozen=True)
class TaskRetryPolicy:
    max_retries: int = 0


@dataclass
class TaskRequest:
    task_type: str
    trigger_source: str
    requested_by: str = ""
    input_payload: dict[str, Any] = field(default_factory=dict)
    scope: str = ""
    artifact_uri: str = ""
    idempotency_key: str = ""
    retry_policy: TaskRetryPolicy = field(default_factory=TaskRetryPolicy)

    def __post_init__(self) -> None:
        self.task_type = self.task_type.strip()
        self.trigger_source = self.trigger_source.strip() or "manual"
        self.requested_by = self.requested_by.strip()
        self.scope = self.scope.strip()
        self.artifact_uri = self.artifact_uri.strip()
        if not self.idempotency_key:
            self.idempotency_key = build_task_idempotency_key(
                task_type=self.task_type,
                trigger_source=self.trigger_source,
                scope=self.scope,
                input_payload=self.input_payload,
            )


@dataclass(frozen=True)
class TaskExecutionRecord:
    task_id: str
    task_type: str
    task_status: str
    trigger_source: str
    requested_by: str
    idempotency_key: str
    scope: str
    artifact_uri: str
    input_payload: dict[str, Any]
    result_payload: dict[str, Any]
    max_retries: int
    retry_count: int
    started_at: int
    finished_at: int | None
    error_code: str = ""
    error_message: str = ""
