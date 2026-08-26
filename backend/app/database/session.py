from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.core.logging import logger
from app.database.base import Base

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session)


def create_database_tables() -> None:
    import app.models  # noqa: F401

    logger.info("Ensuring database tables exist")
    Base.metadata.create_all(bind=engine)
    ensure_development_schema()


def check_database_connection() -> None:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))


def ensure_development_schema() -> None:
    """Keep the MVP database usable before Alembic migrations are introduced."""
    statements = [
        "ALTER TABLE summaries ADD COLUMN IF NOT EXISTS title VARCHAR(500)",
        "ALTER TABLE summaries ADD COLUMN IF NOT EXISTS key_points JSON NOT NULL DEFAULT '[]'",
        "ALTER TABLE summaries ADD COLUMN IF NOT EXISTS important_quotes JSON NOT NULL DEFAULT '[]'",
        "ALTER TABLE summaries ADD COLUMN IF NOT EXISTS timeline JSON NOT NULL DEFAULT '[]'",
        "ALTER TABLE summaries ADD COLUMN IF NOT EXISTS action_items JSON NOT NULL DEFAULT '[]'",
        "ALTER TABLE summaries ADD COLUMN IF NOT EXISTS difficulty_level VARCHAR(80)",
        "ALTER TABLE summaries ADD COLUMN IF NOT EXISTS target_audience VARCHAR(255)",
        "ALTER TABLE summaries ADD COLUMN IF NOT EXISTS analysis_json JSON NOT NULL DEFAULT '{}'",
    ]

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
