"""PostgreSQL backend helpers."""

from __future__ import annotations

from sqlalchemy.engine import Engine

from products.tech_blog_monitor.db.engine import create_engine_for_url


def create_postgres_engine(database_url: str) -> Engine:
    return create_engine_for_url(database_url)
