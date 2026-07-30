from fastapi import APIRouter

from app.api.v1.routes import chat, system, videos

api_router = APIRouter()
api_router.include_router(system.router, tags=["系统"])
api_router.include_router(videos.router, prefix="/videos", tags=["视频"])
api_router.include_router(chat.router, prefix="/chat", tags=["问答"])
