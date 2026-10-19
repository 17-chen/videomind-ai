"""Add user edits and index synchronization state.

Revision ID: 20261020_0006
Revises: 20261019_0005
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20261020_0006"
down_revision: str | None = "20261019_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("videos", sa.Column("user_category", sa.String(length=120), nullable=True))
    op.add_column("videos", sa.Column("index_sync_error", sa.Text(), nullable=True))
    op.add_column("summaries", sa.Column("note_is_manual", sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade() -> None:
    op.drop_column("summaries", "note_is_manual")
    op.drop_column("videos", "index_sync_error")
    op.drop_column("videos", "user_category")
