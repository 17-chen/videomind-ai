from fastapi import APIRouter, HTTPException, status

from app.core.config import settings
from app.database.session import check_database_connection
from app.services.vector_store import vector_store

router = APIRouter()


def check_vector_store_connection() -> None:
    vector_store.check_connection()


@router.get("/health", summary="API 健康检查", description="检查 API v1 服务是否正常运行。")
def api_health_check() -> dict[str, str]:
    return {"status": "ok", "environment": settings.app_env, "language": settings.default_language}


@router.get("/health/live", summary="存活检查", description="仅检查 API 进程是否能够响应。")
def liveness_check() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}


@router.get("/health/ready", summary="就绪检查", description="检查 PostgreSQL 与向量库是否已就绪。")
def readiness_check() -> dict[str, str]:
    try:
        check_database_connection()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="数据库尚未就绪",
        ) from exc
    try:
        check_vector_store_connection()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="向量知识库尚未就绪",
        ) from exc
    return {"status": "ready", "database": "ok", "vector_store": "ok"}
