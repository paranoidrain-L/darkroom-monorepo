# -*- coding: utf-8 -*-
"""Conversation logging and redaction helpers for Feishu bot."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from typing import Any, Optional

SENSITIVE_PATTERNS = (
    r"(?i)(api[_-]?key\s*[:=]\s*)[^\s,，;；]+",
    r"(?i)(token\s*[:=]\s*)[^\s,，;；]+",
    r"(?i)(password\s*[:=]\s*)[^\s,，;；]+",
    r"(?i)(secret\s*[:=]\s*)[^\s,，;；]+",
    r"(?i)(authorization:\s*bearer\s+)[^\s,，;；]+",
)


def redact_sensitive_text(text: str) -> str:
    redacted = text
    for pattern in SENSITIVE_PATTERNS:
        redacted = re.sub(pattern, r"\1[REDACTED]", redacted)
    return redacted


def redact_sensitive_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_sensitive_text(value)
    if isinstance(value, dict):
        return {key: redact_sensitive_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_sensitive_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_sensitive_value(item) for item in value)
    return value


class ConversationLogger:
    """Append-only JSONL conversation log."""

    def __init__(self, log_dir: str = "logs/conversations") -> None:
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)

    def log_conversation(
        self,
        *,
        user_id: str,
        user_message: str,
        ai_response: str,
        message_id: Optional[str] = None,
        trace: dict[str, Any] | None = None,
        redact: bool = True,
    ) -> str:
        timestamp = datetime.now()
        log_file = os.path.join(self.log_dir, f"{timestamp:%Y-%m-%d}.jsonl")
        log_entry = {
            "timestamp": timestamp.isoformat(),
            "user_id": user_id,
            "message_id": message_id,
            "user_message": redact_sensitive_text(user_message) if redact else user_message,
            "ai_response": redact_sensitive_text(ai_response) if redact else ai_response,
        }
        if trace is not None:
            log_entry["trace"] = redact_sensitive_value(trace) if redact else trace
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
        return log_file
