"""Per-user encrypted AI settings.

Revision ID: 20261008_0003
Revises: 20260904_0002
"""
from collections.abc import Sequence
from alembic import op
import sqlalchemy as sa

revision: str = "20261008_0003"
down_revision: str | None = "20260904_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_settings",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("encrypted_api_key", sa.String(length=2000), nullable=False),
        sa.Column("encrypted_asr_api_key", sa.String(length=2000), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("ai_settings")
