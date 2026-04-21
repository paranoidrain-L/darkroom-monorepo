"""tech blog postgres ready baseline

Revision ID: 0001_tech_blog
Revises:
Create Date: 2026-04-16 17:30:00
"""

from __future__ import annotations

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from alembic import op

revision = "0001_tech_blog"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect_name = bind.dialect.name
    if dialect_name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "meta",
        sa.Column("key", sa.String(), primary_key=True),
        sa.Column("value", sa.String(), nullable=False),
    )
    op.create_table(
        "runs",
        sa.Column("run_id", sa.String(), primary_key=True),
        sa.Column("generated_at", sa.Integer(), nullable=False),
        sa.Column("generated_at_iso", sa.String(), nullable=False),
        sa.Column("output_path", sa.String(), nullable=False),
        sa.Column("view", sa.String(), nullable=False),
        sa.Column("incremental_mode", sa.String(), nullable=False),
        sa.Column("article_count", sa.Integer(), nullable=False),
        sa.Column("all_article_count", sa.Integer(), nullable=False),
        sa.Column("new_article_count", sa.Integer(), nullable=False),
    )
    op.create_index("ix_runs_generated_at", "runs", ["generated_at"])
    op.create_table(
        "articles",
        sa.Column("article_id", sa.String(), primary_key=True),
        sa.Column("normalized_url", sa.String(), nullable=False, unique=True),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("source_id", sa.String(), nullable=False),
        sa.Column("source_name", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("published_ts", sa.Integer(), nullable=True),
        sa.Column("first_seen_at", sa.Integer(), nullable=False),
        sa.Column("last_seen_at", sa.Integer(), nullable=False),
        sa.Column("latest_fetched_at", sa.Integer(), nullable=False),
        sa.Column("rss_summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("ai_summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("content_hash", sa.String(), nullable=False),
        sa.Column("last_run_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.Integer(), nullable=False),
    )
    op.create_index("ix_articles_source_name", "articles", ["source_name"])
    op.create_index("ix_articles_category", "articles", ["category"])
    op.create_index("ix_articles_published_ts", "articles", ["published_ts"])
    op.create_table(
        "run_articles",
        sa.Column("run_id", sa.String(), sa.ForeignKey("runs.run_id"), nullable=False),
        sa.Column("article_id", sa.String(), sa.ForeignKey("articles.article_id"), nullable=False),
        sa.Column("normalized_url", sa.String(), nullable=False),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("source_name", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("published_ts", sa.Integer(), nullable=True),
        sa.Column("fetched_at", sa.Integer(), nullable=False),
        sa.Column("is_new", sa.Integer(), nullable=False),
        sa.Column("in_report", sa.Integer(), nullable=False),
        sa.Column("report_position", sa.Integer(), nullable=True),
        sa.Column("rss_summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("ai_summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("content_hash", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("run_id", "article_id"),
    )
    op.create_index("idx_run_articles_run_id", "run_articles", ["run_id"])
    op.create_index("idx_run_articles_report_position", "run_articles", ["run_id", "report_position"])
    op.create_table(
        "article_contents",
        sa.Column("article_id", sa.String(), sa.ForeignKey("articles.article_id"), primary_key=True),
        sa.Column("content_status", sa.String(), nullable=False, server_default="not_fetched"),
        sa.Column("content_source", sa.String(), nullable=False, server_default=""),
        sa.Column("clean_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("raw_html", sa.Text(), nullable=False, server_default=""),
        sa.Column("content_error", sa.Text(), nullable=False, server_default=""),
        sa.Column("content_http_status", sa.Integer(), nullable=True),
        sa.Column("content_fetched_at", sa.Integer(), nullable=True),
        sa.Column("content_final_url", sa.String(), nullable=False, server_default=""),
        sa.Column("updated_at", sa.Integer(), nullable=False),
    )
    op.create_table(
        "article_enrichments",
        sa.Column("article_id", sa.String(), sa.ForeignKey("articles.article_id"), primary_key=True),
        sa.Column("one_line_summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("key_points_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("why_it_matters", sa.Text(), nullable=False, server_default=""),
        sa.Column("recommended_for_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("tags_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("topic", sa.String(), nullable=False, server_default=""),
        sa.Column("enrichment_status", sa.String(), nullable=False, server_default="not_enriched"),
        sa.Column("enrichment_error", sa.Text(), nullable=False, server_default=""),
        sa.Column("updated_at", sa.Integer(), nullable=False),
    )
    op.create_table(
        "article_chunks",
        sa.Column("chunk_id", sa.String(), primary_key=True),
        sa.Column("article_id", sa.String(), sa.ForeignKey("articles.article_id"), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("source_kind", sa.String(), nullable=False, server_default=""),
        sa.Column("text", sa.Text(), nullable=False, server_default=""),
        sa.Column("embedding_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("updated_at", sa.Integer(), nullable=False),
        sa.UniqueConstraint("article_id", "chunk_index", name="uq_article_chunks_article_index"),
    )
    op.create_index("idx_article_chunks_article_id", "article_chunks", ["article_id"])
    op.create_table(
        "deliveries",
        sa.Column("delivery_id", sa.String(), primary_key=True),
        sa.Column("run_id", sa.String(), sa.ForeignKey("runs.run_id"), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("cadence", sa.String(), nullable=False),
        sa.Column("dedupe_key", sa.String(), nullable=False, unique=True),
        sa.Column("payload_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=False, server_default=""),
        sa.Column("delivered_at", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.Integer(), nullable=False),
    )
    op.create_index("ix_deliveries_run_id", "deliveries", ["run_id"])
    op.create_index("ix_deliveries_status", "deliveries", ["status"])
    op.create_table(
        "feedback",
        sa.Column("feedback_id", sa.String(), primary_key=True),
        sa.Column("run_id", sa.String(), sa.ForeignKey("runs.run_id"), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("feedback_type", sa.String(), nullable=False),
        sa.Column("feedback_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.Integer(), nullable=False),
    )
    op.create_index("ix_feedback_run_id", "feedback", ["run_id"])
    op.create_table(
        "article_search_documents",
        sa.Column("article_id", sa.String(), sa.ForeignKey("articles.article_id"), primary_key=True),
        sa.Column("title", sa.String(), nullable=False, server_default=""),
        sa.Column("url", sa.String(), nullable=False, server_default=""),
        sa.Column("source_name", sa.String(), nullable=False, server_default=""),
        sa.Column("category", sa.String(), nullable=False, server_default=""),
        sa.Column("published_ts", sa.Integer(), nullable=True),
        sa.Column("rss_summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("ai_summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("one_line_summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("why_it_matters", sa.Text(), nullable=False, server_default=""),
        sa.Column("topic", sa.String(), nullable=False, server_default=""),
        sa.Column("tags_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("clean_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("document_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("updated_at", sa.Integer(), nullable=False),
    )
    op.create_table(
        "chunk_embedding_records",
        sa.Column("chunk_id", sa.String(), primary_key=True),
        sa.Column("article_id", sa.String(), sa.ForeignKey("articles.article_id"), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=False, server_default=""),
        sa.Column("url", sa.String(), nullable=False, server_default=""),
        sa.Column("source_name", sa.String(), nullable=False, server_default=""),
        sa.Column("category", sa.String(), nullable=False, server_default=""),
        sa.Column("topic", sa.String(), nullable=False, server_default=""),
        sa.Column("published_ts", sa.Integer(), nullable=True),
        sa.Column("source_kind", sa.String(), nullable=False, server_default=""),
        sa.Column("text", sa.Text(), nullable=False, server_default=""),
        sa.Column("document_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("embedding_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column(
            "embedding_vector",
            sa.Text() if dialect_name != "postgresql" else Vector(64),
            nullable=True,
        ),
        sa.Column("updated_at", sa.Integer(), nullable=False),
    )
    op.create_index("ix_chunk_embedding_records_article_id", "chunk_embedding_records", ["article_id"])
    op.create_index("ix_chunk_embedding_records_published_ts", "chunk_embedding_records", ["published_ts"])
    if dialect_name == "postgresql":
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_article_search_documents_fts "
            "ON article_search_documents USING GIN (to_tsvector('simple', coalesce(document_text, '')))"
        )


def downgrade() -> None:
    bind = op.get_bind()
    dialect_name = bind.dialect.name
    if dialect_name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_article_search_documents_fts")
    op.drop_table("chunk_embedding_records")
    op.drop_table("article_search_documents")
    op.drop_index("ix_feedback_run_id", table_name="feedback")
    op.drop_table("feedback")
    op.drop_index("ix_deliveries_status", table_name="deliveries")
    op.drop_index("ix_deliveries_run_id", table_name="deliveries")
    op.drop_table("deliveries")
    op.drop_index("idx_article_chunks_article_id", table_name="article_chunks")
    op.drop_table("article_chunks")
    op.drop_table("article_enrichments")
    op.drop_table("article_contents")
    op.drop_index("idx_run_articles_report_position", table_name="run_articles")
    op.drop_index("idx_run_articles_run_id", table_name="run_articles")
    op.drop_table("run_articles")
    op.drop_index("ix_articles_published_ts", table_name="articles")
    op.drop_index("ix_articles_category", table_name="articles")
    op.drop_index("ix_articles_source_name", table_name="articles")
    op.drop_table("articles")
    op.drop_index("ix_runs_generated_at", table_name="runs")
    op.drop_table("runs")
    op.drop_table("meta")
