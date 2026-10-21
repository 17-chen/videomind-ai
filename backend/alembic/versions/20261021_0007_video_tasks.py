"""Persist video processing tasks.

Revision ID: 20261021_0007
Revises: 20261020_0006
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20261021_0007"
down_revision: str | None = "20261020_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("video_tasks"):
        expected = {
            "id", "video_id", "user_id", "kind", "status", "stage", "attempts", "error",
            "worker_id", "lease_expires_at", "cancel_requested_at", "started_at",
            "finished_at", "created_at", "updated_at",
        }
        columns = {column["name"]: column for column in inspector.get_columns("video_tasks")}
        if set(columns) != expected:
            raise RuntimeError("video_tasks 表结构与迁移不一致，请先人工检查")
        expected_types = {
            "id": sa.String, "video_id": sa.String, "user_id": sa.String,
            "kind": sa.String, "status": sa.String, "stage": sa.String,
            "attempts": sa.Integer, "error": sa.Text, "worker_id": sa.String,
            "lease_expires_at": sa.DateTime, "cancel_requested_at": sa.DateTime,
            "started_at": sa.DateTime, "finished_at": sa.DateTime,
            "created_at": sa.DateTime, "updated_at": sa.DateTime,
        }
        if any(not isinstance(columns[name]["type"], expected_type) for name, expected_type in expected_types.items()):
            raise RuntimeError("video_tasks 字段类型与迁移不一致，请先人工检查")
        indexes = {index["name"]: index for index in inspector.get_indexes("video_tasks")}
        required = {"ix_video_tasks_video_id", "ix_video_tasks_user_id", "ix_video_tasks_status", "uq_video_tasks_active_video"}
        if not required.issubset(indexes) or not indexes["uq_video_tasks_active_video"]["unique"]:
            raise RuntimeError("video_tasks 索引与迁移不一致，请先人工检查")
        foreign_keys = {(key["constrained_columns"][0], key["referred_table"]) for key in inspector.get_foreign_keys("video_tasks")}
        if not {("video_id", "videos"), ("user_id", "users")}.issubset(foreign_keys):
            raise RuntimeError("video_tasks 外键与迁移不一致，请先人工检查")
        op.alter_column("video_tasks", "attempts", server_default="0")
        return
    op.create_table(
        "video_tasks",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("video_id", sa.String(length=36), sa.ForeignKey("videos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("stage", sa.String(length=20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("worker_id", sa.String(length=120), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_video_tasks_video_id", "video_tasks", ["video_id"])
    op.create_index("ix_video_tasks_user_id", "video_tasks", ["user_id"])
    op.create_index("ix_video_tasks_status", "video_tasks", ["status"])
    op.create_index(
        "uq_video_tasks_active_video", "video_tasks", ["video_id"], unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running')"),
        sqlite_where=sa.text("status IN ('queued', 'running')"),
    )


def downgrade() -> None:
    op.drop_index("uq_video_tasks_active_video", table_name="video_tasks")
    op.drop_index("ix_video_tasks_status", table_name="video_tasks")
    op.drop_index("ix_video_tasks_user_id", table_name="video_tasks")
    op.drop_index("ix_video_tasks_video_id", table_name="video_tasks")
    op.drop_table("video_tasks")
