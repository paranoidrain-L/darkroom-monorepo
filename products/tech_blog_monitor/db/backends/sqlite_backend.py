"""SQLite backend helpers."""

from __future__ import annotations

from sqlalchemy.engine import Engine

from products.tech_blog_monitor.db.engine import build_sqlite_url, create_engine_for_url


def create_sqlite_engine(asset_db_path: str) -> Engine:
    return create_engine_for_url(build_sqlite_url(asset_db_path))
