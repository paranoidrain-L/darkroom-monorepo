"""DB engine helpers for tech_blog_monitor."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from products.tech_blog_monitor.config import TechBlogMonitorConfig


def build_sqlite_url(asset_db_path: str) -> str:
    return f"sqlite+pysqlite:///{Path(asset_db_path).expanduser().resolve()}"


def resolve_database_url(
    *,
    config: TechBlogMonitorConfig | None = None,
    database_url: str = "",
    asset_db_path: str = "",
) -> str:
    chosen_database_url = database_url or (config.database_url if config is not None else "")
    if chosen_database_url.strip():
        return chosen_database_url.strip()

    chosen_asset_db_path = asset_db_path or (config.asset_db_path if config is not None else "")
    if chosen_asset_db_path.strip():
        return build_sqlite_url(chosen_asset_db_path.strip())

    raise ValueError("asset db not configured: set TECH_BLOG_ASSET_DB_PATH or TECH_BLOG_DATABASE_URL")


def create_engine_for_url(database_url: str) -> Engine:
    if database_url.startswith("sqlite"):
        return create_engine(
            database_url,
            future=True,
            connect_args={"check_same_thread": False},
        )
    return create_engine(database_url, future=True)


def create_session_factory(database_url: str) -> sessionmaker[Session]:
    engine = create_engine_for_url(database_url)
    return sessionmaker(bind=engine, autoflush=False, future=True)
