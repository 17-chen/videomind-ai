from fastapi import APIRouter

from app.core.config import settings

router = APIRouter()


@router.get("/health", summary="API 健康检查", description="检查 API v1 服务是否正常运行。")
def api_health_check() -> dict[str, str]:
    return {"status": "ok", "environment": settings.app_env, "language": settings.default_language}
