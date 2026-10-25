from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.core.i18n import t
from app.core.logging import configure_logging, logger
from app.database.session import SessionLocal, create_database_tables
from app.services.videos import recover_interrupted_videos


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
    if not settings.is_production and settings.recover_interrupted_tasks_on_startup:
        with SessionLocal() as db:
            recovered = recover_interrupted_videos(db)
        if recovered:
            logger.warning("Marked {} interrupted local video tasks retryable", recovered)
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
    expose_headers=["X-Request-ID"],
)


@app.middleware("http")
async def trace_request(request: Request, call_next):
    request_id = uuid4().hex
    request.state.request_id = request_id
    started = perf_counter()
    status_code = 500
    try:
        try:
            response = await call_next(request)
        except Exception as exc:
            logger.error("Unhandled error request_id={} type={}", request_id, type(exc).__name__)
            response = JSONResponse(status_code=500, content={"detail": t("internal_server_error")})
        status_code = response.status_code
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        route = request.scope.get("route")
        route_path = getattr(route, "path", "<unmatched>")
        logger.info(
            "HTTP request_id={} method={} route={} status={} duration_ms={:.1f}",
            request_id, request.method, route_path, status_code, (perf_counter() - started) * 1000,
        )


register_exception_handlers(app)
app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/", include_in_schema=False)
def api_root() -> RedirectResponse:
    return RedirectResponse(url="/docs")


@app.get("/health", tags=["系统"], summary="应用健康检查", description="检查 VideoMind AI 后端服务是否正常运行。")
def health_check() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name, "language": settings.default_language}
