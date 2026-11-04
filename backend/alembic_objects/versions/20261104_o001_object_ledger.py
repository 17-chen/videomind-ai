"""Install backend-only object ledger, independently from business migrations."""

from alembic import op
import sqlalchemy as sa

revision = '20261104_o001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'vm_storage_objects',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), nullable=False),
        sa.Column('video_id', sa.String(36), nullable=False),
        sa.Column('kind', sa.String(16), nullable=False),
        sa.Column('filename', sa.String(180), nullable=False),
        sa.Column('bucket', sa.String(100), nullable=False),
        sa.Column('project_fingerprint', sa.String(64), nullable=False),
        sa.Column('sha256', sa.String(64), nullable=False),
        sa.Column('size_bytes', sa.BigInteger(), nullable=False),
        sa.Column('state', sa.String(16), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("state IN ('pending','ready','retired','deleted')", name='ck_storage_state'),
        sa.CheckConstraint("kind IN ('video','audio','transcript','note')", name='ck_storage_kind'),
        sa.CheckConstraint('size_bytes >= 0', name='ck_storage_size'),
    )
    op.create_index('ix_storage_owner_state', 'vm_storage_objects', ['user_id', 'state'])
    op.create_index('uq_storage_ready', 'vm_storage_objects', ['user_id', 'video_id', 'kind', 'filename'], unique=True, postgresql_where=sa.text("state='ready'"))
    op.execute('ALTER TABLE public.vm_storage_objects ENABLE ROW LEVEL SECURITY')
    op.execute('REVOKE ALL ON public.vm_storage_objects FROM PUBLIC')
    connection = op.get_bind()
    for role in ('anon', 'authenticated', 'service_role'):
        if connection.scalar(sa.text('SELECT 1 FROM pg_roles WHERE rolname=:role'), {'role': role}):
            connection.execute(sa.text(f'REVOKE ALL ON public.vm_storage_objects FROM "{role}"'))


def downgrade():
    op.drop_table('vm_storage_objects')
