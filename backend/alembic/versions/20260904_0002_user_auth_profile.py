"""Add external authentication and profile fields to users.

Revision ID: 20260904_0002
Revises: 20260826_0001
Create Date: 2026-09-04
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260904_0002"
down_revision: str | None = "20260826_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("auth_subject", sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("display_name", sa.String(length=120), nullable=True))
    op.add_column("users", sa.Column("avatar_url", sa.String(length=1000), nullable=True))
    op.create_index(op.f("ix_users_auth_subject"), "users", ["auth_subject"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_users_auth_subject"), table_name="users")
    op.drop_column("users", "avatar_url")
    op.drop_column("users", "display_name")
    op.drop_column("users", "auth_subject")
