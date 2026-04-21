# -*- coding: utf-8 -*-
"""Tech Blog Monitor - Phase 7 用户反馈。"""

from __future__ import annotations

from typing import Dict, List, Optional

from products.tech_blog_monitor.repository_provider import open_repository_bundle


def record_feedback(
    db_path: str,
    *,
    run_id: str,
    role: str,
    feedback_type: str,
    feedback_text: str,
    metadata: Optional[Dict[str, object]] = None,
    created_at: int,
    database_url: str = "",
) -> str:
    metadata = metadata or {}
    with open_repository_bundle(asset_db_path=db_path, database_url=database_url) as bundle:
        return bundle.feedback_repository.add_feedback(
            run_id=run_id,
            role=role,
            feedback_type=feedback_type,
            feedback_text=feedback_text,
            metadata=metadata,
            created_at=created_at,
        )


def list_feedback(
    db_path: str,
    *,
    run_id: str = "",
    role: str = "",
    database_url: str = "",
) -> List[Dict[str, object]]:
    with open_repository_bundle(asset_db_path=db_path, database_url=database_url) as bundle:
        return bundle.feedback_repository.list_feedback(
            run_id=run_id or None,
            role=role or None,
        )
