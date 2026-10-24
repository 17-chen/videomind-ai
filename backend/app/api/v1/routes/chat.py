from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db
from app.core.config import settings
from app.models.user import User
from app.schemas.rag import ChatRequest, ChatResponse, ChatSource
from app.services.rag import chat_with_videos
from app.services.request_limits import consume_request, lock_user_for_limits

router = APIRouter()


@router.post(
    "",
    response_model=ChatResponse,
    summary="和我的视频知识库对话",
    description="检索当前用户的视频资料，并使用该用户配置的模型生成回答。",
)
def chat(
    payload: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChatResponse:
    lock_user_for_limits(db, current_user.id)
    consume_request(db, current_user.id, "chat", settings.max_chat_requests_per_minute)
    db.commit()
    result = chat_with_videos(db=db, user=current_user, question=payload.question, limit=payload.limit, language=payload.language)
    return ChatResponse(
        answer=result.answer,
        sources=[ChatSource(**source.__dict__) for source in result.sources],
    )
