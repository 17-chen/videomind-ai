"""Retain explicit remote deletion intent after deleting the business video."""

from alembic import op
import sqlalchemy as sa

revision = '20261105_o002'
down_revision = '20261104_o001'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('vm_storage_objects', sa.Column('delete_requested', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.create_index('ix_storage_cleanup', 'vm_storage_objects', ['state', 'id'], postgresql_where=sa.text('delete_requested'))


def downgrade():
    # Dropping this column would erase unfulfilled deletion requests.
    connection = op.get_bind()
    # Prevent a concurrent business deletion from committing a new intent
    # between the safety check and DROP COLUMN.
    connection.execute(sa.text('LOCK TABLE vm_storage_objects IN ACCESS EXCLUSIVE MODE'))
    if connection.scalar(sa.text("SELECT count(*) FROM vm_storage_objects WHERE delete_requested AND state != 'deleted'")):
        raise RuntimeError('Unfulfilled object deletion requests must be reconciled before downgrade')
    op.drop_index('ix_storage_cleanup', table_name='vm_storage_objects')
    op.drop_column('vm_storage_objects', 'delete_requested')
