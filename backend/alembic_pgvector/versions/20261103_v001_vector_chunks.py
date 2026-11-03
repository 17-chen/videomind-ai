"""Install opt-in vector chunks after business schema migrations and backup."""

from alembic import op
from sqlalchemy import text

revision = "20261103_v001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    namespace = connection.scalar(
        text("""
        SELECT n.nspname FROM pg_extension e JOIN pg_namespace n ON n.oid=e.extnamespace WHERE e.extname='vector'
    """)
    )
    schema = connection.dialect.identifier_preparer.quote_schema(namespace)
    connection.execute(
        text(f"""
        CREATE TABLE public.vm_vector_chunks (
            user_id varchar(36) NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
            video_id varchar(36) NOT NULL REFERENCES public.videos(id) ON DELETE CASCADE,
            model_key varchar(128) NOT NULL,
            dimensions integer NOT NULL CHECK (dimensions > 0 AND dimensions <= 16000),
            chunk_index integer NOT NULL CHECK (chunk_index >= 0),
            title text NOT NULL,
            url text NOT NULL,
            category text,
            source text,
            document text NOT NULL,
            embedding {schema}.vector NOT NULL,
            PRIMARY KEY (user_id, video_id, model_key, chunk_index),
            CHECK (dimensions = {schema}.vector_dims(embedding))
        )
    """)
    )
    connection.execute(
        text(
            "CREATE INDEX ix_vm_vector_chunks_user_model ON public.vm_vector_chunks (user_id, model_key, dimensions)"
        )
    )
    connection.execute(
        text("ALTER TABLE public.vm_vector_chunks ENABLE ROW LEVEL SECURITY")
    )
    connection.execute(text("REVOKE ALL ON public.vm_vector_chunks FROM PUBLIC"))
    # Supabase may grant public-schema privileges through default privileges.
    # Vectors are backend-only; no client/PostgREST role receives table access.
    for role in ("anon", "authenticated", "service_role"):
        if connection.scalar(
            text("SELECT 1 FROM pg_roles WHERE rolname=:role"), {"role": role}
        ):
            connection.execute(
                text(f'REVOKE ALL ON public.vm_vector_chunks FROM "{role}"')
            )


def downgrade():
    op.execute("DROP TABLE public.vm_vector_chunks")
    # Never drop a shared extension; other applications may depend on it.
