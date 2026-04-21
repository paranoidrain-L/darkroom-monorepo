# -*- coding: utf-8 -*-
"""Shared OTLP HTTP helpers."""

from __future__ import annotations

from urllib.parse import urlparse, urlunparse

import requests
from requests.adapters import HTTPAdapter

DEFAULT_OTLP_TIMEOUT_SECONDS = 0.5
DEFAULT_OTLP_EXPORT_INTERVAL_MS = 60_000
DEFAULT_OTLP_EXPORT_TIMEOUT_MS = 500


def build_otlp_http_session() -> requests.Session:
    session = requests.Session()
    adapter = HTTPAdapter(max_retries=0, pool_connections=1, pool_maxsize=1)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def resolve_otlp_endpoint(endpoint: str, *, signal: str) -> str:
    if not endpoint:
        return ""

    parsed = urlparse(endpoint)
    if not parsed.scheme or not parsed.netloc:
        return endpoint

    path = parsed.path.rstrip("/")
    if path.endswith("/v1/traces") or path.endswith("/v1/metrics"):
        path = path.rsplit("/", 1)[0] + f"/{signal}"
    elif not path:
        path = f"/v1/{signal}"
    elif "/v1/" not in path:
        path = f"{path}/v1/{signal}"

    return urlunparse(parsed._replace(path=path))
