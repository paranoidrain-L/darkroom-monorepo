"""Tech Blog Monitor API dependencies。"""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends, HTTPException

from products.tech_blog_monitor.config import TechBlogMonitorConfig
from products.tech_blog_monitor.repository_provider import RepositoryBundle, open_repository_bundle


async def get_config() -> TechBlogMonitorConfig:
    return TechBlogMonitorConfig.from_env()


async def get_asset_db_path(config: TechBlogMonitorConfig = Depends(get_config)) -> str:
    database_url = config.database_url.strip()
    asset_db_path = config.asset_db_path.strip()
    if not asset_db_path and not database_url:
        raise HTTPException(
            status_code=503,
            detail="asset db not configured: set TECH_BLOG_ASSET_DB_PATH or TECH_BLOG_DATABASE_URL",
        )
    return asset_db_path


async def get_repository_bundle(
    config: TechBlogMonitorConfig = Depends(get_config),
) -> AsyncIterator[RepositoryBundle]:
    asset_db_path = config.asset_db_path.strip()
    database_url = config.database_url.strip()
    if not asset_db_path and not database_url:
        raise HTTPException(
            status_code=503,
            detail="asset db not configured: set TECH_BLOG_ASSET_DB_PATH or TECH_BLOG_DATABASE_URL",
        )
    try:
        with open_repository_bundle(
            config=config,
            asset_db_path=asset_db_path,
            database_url=database_url,
        ) as bundle:
            yield bundle
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
