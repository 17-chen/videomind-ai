"""Create the initial VideoMind schema.

Revision ID: 20260826_0001
Revises:
Create Date: 2026-08-26
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260826_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    op.create_table(
        "videos",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("duration", sa.Integer(), nullable=True),
        sa.Column("thumbnail", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("media_path", sa.Text(), nullable=True),
        sa.Column("audio_path", sa.Text(), nullable=True),
        sa.Column("processing_error", sa.Text(), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_videos_source"), "videos", ["source"], unique=False)
    op.create_index(op.f("ix_videos_status"), "videos", ["status"], unique=False)
    op.create_index(op.f("ix_videos_user_id"), "videos", ["user_id"], unique=False)

    op.create_table(
        "transcripts",
        sa.Column("video_id", sa.String(length=36), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_transcripts_video_id"), "transcripts", ["video_id"], unique=True)

    op.create_table(
        "summaries",
        sa.Column("video_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("key_points", sa.JSON(), nullable=False),
        sa.Column("keywords", sa.JSON(), nullable=False),
        sa.Column("category", sa.String(length=120), nullable=True),
        sa.Column("important_quotes", sa.JSON(), nullable=False),
        sa.Column("timeline", sa.JSON(), nullable=False),
        sa.Column("action_items", sa.JSON(), nullable=False),
        sa.Column("difficulty_level", sa.String(length=80), nullable=True),
        sa.Column("target_audience", sa.String(length=255), nullable=True),
        sa.Column("analysis_json", sa.JSON(), nullable=False),
        sa.Column("markdown_note", sa.Text(), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_summaries_category"), "summaries", ["category"], unique=False)
    op.create_index(op.f("ix_summaries_video_id"), "summaries", ["video_id"], unique=True)

    op.create_table(
        "embeddings",
        sa.Column("video_id", sa.String(length=36), nullable=False),
        sa.Column("vector_id", sa.String(length=255), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("vector_id"),
    )
    op.create_index(op.f("ix_embeddings_video_id"), "embeddings", ["video_id"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_embeddings_video_id"), table_name="embeddings")
    op.drop_table("embeddings")
    op.drop_index(op.f("ix_summaries_video_id"), table_name="summaries")
    op.drop_index(op.f("ix_summaries_category"), table_name="summaries")
    op.drop_table("summaries")
    op.drop_index(op.f("ix_transcripts_video_id"), table_name="transcripts")
    op.drop_table("transcripts")
    op.drop_index(op.f("ix_videos_user_id"), table_name="videos")
    op.drop_index(op.f("ix_videos_status"), table_name="videos")
    op.drop_index(op.f("ix_videos_source"), table_name="videos")
    op.drop_table("videos")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
