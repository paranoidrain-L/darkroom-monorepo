"""Repository provider and storage router."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from products.tech_blog_monitor.config import TechBlogMonitorConfig
from products.tech_blog_monitor.db.engine import create_session_factory, resolve_database_url
from products.tech_blog_monitor.db.repositories import (
    ArticleRepository,
    DeliveryRepository,
    FeedbackRepository,
    RetrievalRepository,
    RunRepository,
    SearchRepository,
    TaskRepository,
)


@dataclass
class RepositoryBundle:
    session: Session
    database_url: str
    run_repository: RunRepository
    article_repository: ArticleRepository
    search_repository: SearchRepository
    feedback_repository: FeedbackRepository
    delivery_repository: DeliveryRepository
    retrieval_repository: RetrievalRepository
    task_repository: TaskRepository


def _resolve_sqlite_file_path(database_url: str) -> Path | None:
    url = make_url(database_url)
    if not url.drivername.startswith("sqlite"):
        return None
    if not url.database or url.database == ":memory:":
        return None
    return Path(url.database).expanduser().resolve()


@contextmanager
def open_repository_bundle(
    *,
    config: TechBlogMonitorConfig | None = None,
    asset_db_path: str = "",
    database_url: str = "",
) -> Iterator[RepositoryBundle]:
    resolved_database_url = resolve_database_url(
        config=config,
        database_url=database_url,
        asset_db_path=asset_db_path,
    )
    sqlite_file_path = _resolve_sqlite_file_path(resolved_database_url)
    if sqlite_file_path is not None and not sqlite_file_path.exists():
        raise FileNotFoundError(f"资产库不存在: {sqlite_file_path}")

    session_factory = create_session_factory(resolved_database_url)

    session = session_factory()
    try:
        yield RepositoryBundle(
            session=session,
            database_url=resolved_database_url,
            run_repository=RunRepository(session),
            article_repository=ArticleRepository(session),
            search_repository=SearchRepository(session),
            feedback_repository=FeedbackRepository(session),
            delivery_repository=DeliveryRepository(session),
            retrieval_repository=RetrievalRepository(session),
            task_repository=TaskRepository(session),
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
