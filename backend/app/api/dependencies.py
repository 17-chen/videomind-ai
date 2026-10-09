from collections.abc import Generator

from fastapi import Depends, Header, status
from sqlalchemy.orm import Session

from app.database.session import SessionLocal
from app.models.user import User
from app.core.config import settings
from app.core.errors import ApiError
from app.services.auth import decode_supabase_token
from app.services.users import get_or_create_authenticated_user, get_or_create_demo_user


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
) -> User:
    if not settings.uses_supabase_auth:
        return get_or_create_demo_user(db)

    if not authorization or not authorization.startswith("Bearer "):
        raise ApiError("请先登录后再访问", status.HTTP_401_UNAUTHORIZED)

    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise ApiError("请先登录后再访问", status.HTTP_401_UNAUTHORIZED)

    identity = decode_supabase_token(token)
    return get_or_create_authenticated_user(
        db,
        auth_subject=identity.subject,
        email=identity.email,
        display_name=identity.display_name,
        avatar_url=identity.avatar_url,
    )
