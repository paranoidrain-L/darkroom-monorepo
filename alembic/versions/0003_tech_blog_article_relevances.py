"""add article relevances

Revision ID: 0003_tech_blog_relevance
Revises: 0002_tech_blog_tasks
Create Date: 2026-04-19 01:30:00
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0003_tech_blog_relevance"
down_revision = "0002_tech_blog_tasks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "article_relevances",
        sa.Column("article_id", sa.String(), sa.ForeignKey("articles.article_id"), primary_key=True),
        sa.Column("relevance_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("relevance_level", sa.String(), nullable=False, server_default="not_evaluated"),
        sa.Column("relevance_reasons_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("matched_signals_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("dependency_match_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("topic_match_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("source_priority_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.Integer(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("article_relevances")
