"""Persist per-user request rate windows.

Revision ID: 20261024_0008
Revises: 20261021_0007
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20261024_0008"
down_revision: str | None = "20261021_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("request_windows"):
        columns = {column["name"]: column for column in inspector.get_columns("request_windows")}
        expected = {"user_id": sa.String, "action": sa.String, "window_started_at": sa.DateTime, "request_count": sa.Integer}
        primary_key = inspector.get_pk_constraint("request_windows")["constrained_columns"]
        foreign_keys = inspector.get_foreign_keys("request_windows")
        if (
            set(columns) != set(expected)
            or any(not isinstance(columns[name]["type"], kind) for name, kind in expected.items())
            or set(primary_key) != {"user_id", "action"}
            or not any(key["constrained_columns"] == ["user_id"] and key["referred_table"] == "users" for key in foreign_keys)
        ):
            raise RuntimeError("request_windows 表结构与迁移不一致，请先人工检查")
        return
    op.create_table(
        "request_windows",
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("action", sa.String(length=32), primary_key=True),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("request_windows")
