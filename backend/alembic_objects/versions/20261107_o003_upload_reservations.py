"""Reserve uploaded-source bytes before remote transfer, with no visible Video."""

from alembic import op
import sqlalchemy as sa

revision = '20261107_o003'
down_revision = '20261105_o002'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('vm_storage_objects', sa.Column('is_source_upload', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    # Backfill only exact, owned ready references from any prior controlled trial.
    # Do not infer ownership/purpose from names or mark ambiguous pending rows.
    op.execute("""UPDATE public.vm_storage_objects AS o SET is_source_upload = true
        FROM public.videos AS v WHERE v.user_id=o.user_id AND v.id=o.video_id
        AND v.source='upload' AND v.media_path='object://' || o.id
        AND o.kind='video' AND o.state='ready'""")
    op.create_index('uq_storage_pending_upload', 'vm_storage_objects', ['user_id', 'sha256'], unique=True,
                    postgresql_where=sa.text("is_source_upload AND state='pending'"))


def downgrade():
    connection = op.get_bind()
    connection.execute(sa.text('LOCK TABLE vm_storage_objects IN ACCESS EXCLUSIVE MODE'))
    if connection.scalar(sa.text("SELECT count(*) FROM vm_storage_objects WHERE is_source_upload AND state != 'deleted'")):
        raise RuntimeError('Upload reservations and source accounting must be reconciled before downgrade')
    op.drop_index('uq_storage_pending_upload', table_name='vm_storage_objects')
    op.drop_column('vm_storage_objects', 'is_source_upload')
