"""Add timestamp defaults for previously created AI settings tables.

Revision ID: 20261008_0004
Revises: 20261008_0003
"""
from collections.abc import Sequence
from alembic import op
import sqlalchemy as sa

revision: str = "20261008_0004"
down_revision: str | None = "20261008_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

def upgrade() -> None:
    op.alter_column("ai_settings", "created_at", server_default=sa.func.now())
    op.alter_column("ai_settings", "updated_at", server_default=sa.func.now())

def downgrade() -> None:
    op.alter_column("ai_settings", "updated_at", server_default=None)
    op.alter_column("ai_settings", "created_at", server_default=None)
