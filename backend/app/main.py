from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging, logger
from app.database.session import create_database_tables


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    logger.info("Starting {}", settings.app_name)
    if settings.auto_create_database_tables:
        if settings.is_production:
            logger.warning("AUTO_CREATE_DATABASE_TABLES is enabled in production; use Alembic migrations instead")
        create_database_tables()
    else:
        logger.info("Skipping automatic table creation; database schema is managed by Alembic")
    yield
    logger.info("Stopping {}", settings.app_name)


app = FastAPI(
    title=settings.app_name,
    version="0.2.0",
    summary="AI 视频知识管理平台",
    description="把收藏但没时间看的视频，自动转化为个人知识资产。",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)
app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/health", tags=["系统"], summary="应用健康检查", description="检查 VideoMind AI 后端服务是否正常运行。")
def health_check() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name, "language": settings.default_language}
