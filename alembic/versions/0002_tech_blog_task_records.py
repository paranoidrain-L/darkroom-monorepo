"""add task records

Revision ID: 0002_tech_blog_tasks
Revises: 0001_tech_blog
Create Date: 2026-04-17 18:40:00
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0002_tech_blog_tasks"
down_revision = "0001_tech_blog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "task_records",
        sa.Column("task_id", sa.String(), primary_key=True),
        sa.Column("task_type", sa.String(), nullable=False),
        sa.Column("task_status", sa.String(), nullable=False),
        sa.Column("trigger_source", sa.String(), nullable=False),
        sa.Column("requested_by", sa.String(), nullable=False, server_default=""),
        sa.Column("idempotency_key", sa.String(), nullable=False),
        sa.Column("scope", sa.String(), nullable=False, server_default=""),
        sa.Column("artifact_uri", sa.String(), nullable=False, server_default=""),
        sa.Column("input_payload_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("result_payload_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.Integer(), nullable=False),
        sa.Column("finished_at", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(), nullable=False, server_default=""),
        sa.Column("error_message", sa.Text(), nullable=False, server_default=""),
    )
    op.create_index("ix_task_records_task_type", "task_records", ["task_type"])
    op.create_index("ix_task_records_task_status", "task_records", ["task_status"])
    op.create_index("ix_task_records_trigger_source", "task_records", ["trigger_source"])
    op.create_index("ix_task_records_idempotency_key", "task_records", ["idempotency_key"])
    op.create_index("ix_task_records_started_at", "task_records", ["started_at"])


def downgrade() -> None:
    op.drop_index("ix_task_records_started_at", table_name="task_records")
    op.drop_index("ix_task_records_idempotency_key", table_name="task_records")
    op.drop_index("ix_task_records_trigger_source", table_name="task_records")
    op.drop_index("ix_task_records_task_status", table_name="task_records")
    op.drop_index("ix_task_records_task_type", table_name="task_records")
    op.drop_table("task_records")
