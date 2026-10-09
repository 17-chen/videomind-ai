from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from app.core.config import settings


INITIAL_REVISION = "20260826_0001"
INITIAL_TABLES = {"users", "videos", "transcripts", "summaries", "embeddings"}


def migrate() -> None:
    engine = create_engine(settings.database_url)
    try:
        tables = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()

    config = Config("alembic.ini")
    if "alembic_version" not in tables and tables:
        missing = INITIAL_TABLES - tables
        if missing:
            names = ", ".join(sorted(missing))
            raise RuntimeError(f"数据库存在旧结构但缺少核心表：{names}。请先备份并人工检查。")
        command.stamp(config, INITIAL_REVISION)

    command.upgrade(config, "head")


if __name__ == "__main__":
    migrate()
