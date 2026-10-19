"""Track uploaded content hashes per user for duplicate protection.

Revision ID: 20261019_0005
Revises: 20261008_0004
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20261019_0005"
down_revision: str | None = "20261008_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("videos", sa.Column("upload_sha256", sa.String(length=64), nullable=True))
    op.create_unique_constraint("uq_videos_user_upload_sha256", "videos", ["user_id", "upload_sha256"])


def downgrade() -> None:
    op.drop_constraint("uq_videos_user_upload_sha256", "videos", type_="unique")
    op.drop_column("videos", "upload_sha256")
