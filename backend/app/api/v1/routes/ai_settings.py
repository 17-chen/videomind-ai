from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session
from app.api.dependencies import get_current_user, get_db
from app.models.user import User
from app.schemas.ai_settings import AiSettingsRead, AiSettingsWrite
from app.services.ai_settings import delete_settings, public_settings, save_settings

router = APIRouter()


@router.get("/ai", response_model=AiSettingsRead)
def get_ai_settings(current_user: User = Depends(get_current_user)) -> AiSettingsRead:
    return public_settings(current_user)


@router.put("/ai", response_model=AiSettingsRead)
def put_ai_settings(
    payload: AiSettingsWrite,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AiSettingsRead:
    return save_settings(db, current_user, payload)


@router.delete("/ai", status_code=status.HTTP_204_NO_CONTENT)
def remove_ai_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    delete_settings(db, current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
