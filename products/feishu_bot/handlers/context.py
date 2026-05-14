# -*- coding: utf-8 -*-
"""Session context management for file -> text workflows."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

SessionKey = tuple[str, str, str, str, str] | str


@dataclass
class FileInfo:
    """Pending file information kept between two user messages."""

    file_path: str
    file_name: str
    file_kind: str
    file_content: str


@dataclass
class SessionContext:
    """Per-conversation session state."""

    session_key: SessionKey
    pending_file: FileInfo | None = None
    file_timestamp: float = 0.0
    ttl: float = 300.0

    def is_file_expired(self) -> bool:
        if not self.pending_file:
            return True
        return time.time() - self.file_timestamp > self.ttl


class SessionContextManager:
    """Thread-safe in-memory session state."""

    def __init__(self, default_ttl: float = 300):
        self._sessions: dict[SessionKey, SessionContext] = {}
        self._default_ttl = default_ttl
        self._lock = threading.Lock()

    def get_session(self, session_key: SessionKey) -> SessionContext:
        with self._lock:
            return self._get_or_create_session(session_key)

    def set_pending_file(self, session_key: SessionKey, file_info: FileInfo) -> None:
        with self._lock:
            session = self._get_or_create_session(session_key)
            session.pending_file = file_info
            session.file_timestamp = time.time()

    def get_pending_file(self, session_key: SessionKey) -> FileInfo | None:
        with self._lock:
            session = self._find_session(session_key) or self._get_or_create_session(session_key)
            if session.is_file_expired():
                session.pending_file = None
                return None
            return session.pending_file

    def pop_pending_file(self, session_key: SessionKey) -> FileInfo | None:
        with self._lock:
            session = self._find_session(session_key) or self._get_or_create_session(session_key)
            if session.is_file_expired():
                session.pending_file = None
                return None
            pending = session.pending_file
            session.pending_file = None
            return pending

    def clear_pending_file(self, session_key: SessionKey) -> None:
        with self._lock:
            session = self._find_session(session_key) or self._get_or_create_session(session_key)
            session.pending_file = None

    def has_pending_file(self, session_key: SessionKey) -> bool:
        return self.get_pending_file(session_key) is not None

    def _get_or_create_session(self, session_key: SessionKey) -> SessionContext:
        if session_key not in self._sessions:
            self._sessions[session_key] = SessionContext(session_key=session_key, ttl=self._default_ttl)
        return self._sessions[session_key]

    def _find_session(self, session_key: SessionKey) -> SessionContext | None:
        return self._sessions.get(session_key)
