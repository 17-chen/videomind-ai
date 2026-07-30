from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db
from app.models.user import User
from app.schemas.rag import ChatRequest, ChatResponse, ChatSource
from app.services.rag import chat_with_videos

router = APIRouter()


@router.post(
    "",
    response_model=ChatResponse,
    summary="和我的视频知识库对话",
    description="基于 ChromaDB 检索当前用户相关视频内容，并调用 DeepSeek 生成中文回答。",
)
def chat(
    payload: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChatResponse:
    result = chat_with_videos(db=db, user=current_user, question=payload.question, limit=payload.limit)
    return ChatResponse(
        answer=result.answer,
        sources=[ChatSource(**source.__dict__) for source in result.sources],
    )
