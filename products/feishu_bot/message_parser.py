# -*- coding: utf-8 -*-
"""Feishu event parsing helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass
class MessageEnvelope:
    """Normalized event payload for processing."""

    message_id: str
    message_type: str
    content: str
    sender_id: str
    sender_type: str
    chat_id: str
    chat_type: str
    event_type: str


def extract_message_info(payload: dict[str, Any]) -> MessageEnvelope | None:
    header = payload.get("header") or {}
    event_type = header.get("event_type") or payload.get("event_type") or ""
    if event_type and "message.receive" not in event_type:
        return None

    event = payload.get("event") or {}
    message = event.get("message") or {}
    sender = event.get("sender") or {}
    sender_id_info = sender.get("sender_id") or {}
    sender_id = sender_id_info.get("open_id") or sender_id_info.get("user_id") or "unknown"

    if not message:
        return None

    return MessageEnvelope(
        message_id=message.get("message_id", ""),
        message_type=message.get("message_type", ""),
        content=message.get("content", "{}"),
        sender_id=sender_id,
        sender_type=sender.get("sender_type", ""),
        chat_id=message.get("chat_id", ""),
        chat_type=message.get("chat_type", ""),
        event_type=event_type,
    )


def extract_text(content: str) -> str:
    try:
        content_dict = json.loads(content) if isinstance(content, str) else content
    except json.JSONDecodeError:
        return ""
    return str(content_dict.get("text", "")).strip()
