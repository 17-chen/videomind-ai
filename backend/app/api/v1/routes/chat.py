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
    description="检索当前用户的视频资料，并使用该用户配置的模型生成回答。",
)
def chat(
    payload: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChatResponse:
    result = chat_with_videos(db=db, user=current_user, question=payload.question, limit=payload.limit, language=payload.language)
    return ChatResponse(
        answer=result.answer,
        sources=[ChatSource(**source.__dict__) for source in result.sources],
    )
