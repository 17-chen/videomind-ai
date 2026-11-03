"""Independent opt-in vector schema; does not advance the business schema head."""

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import settings

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))


def run(connection):
    if connection.dialect.name != "postgresql":
        raise RuntimeError("pgvector requires PostgreSQL")
    context.configure(connection=connection, version_table="alembic_version_pgvector")
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    raise RuntimeError("pgvector preparation requires an online extension/schema check")

provided = config.attributes.get("connection")
if provided is not None:
    run(provided)
else:
    engine = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    try:
        with engine.connect() as connection:
            run(connection)
    finally:
        engine.dispose()
