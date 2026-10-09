from fastapi import status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ApiError
from app.models.user import User


def get_or_create_demo_user(db: Session) -> User:
    user = db.scalar(select(User).where(User.email == settings.demo_user_email))
    if user is not None:
        return user

    user = User(email=settings.demo_user_email, password_hash=settings.demo_user_password_hash)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_or_create_authenticated_user(
    db: Session,
    *,
    auth_subject: str,
    email: str,
    display_name: str | None = None,
    avatar_url: str | None = None,
) -> User:
    user = db.scalar(select(User).where(User.auth_subject == auth_subject))
    email_owner = db.scalar(select(User).where(User.email == email))

    # Email alone does not prove ownership of a pre-existing local account.
    # In particular, a Supabase signup must never inherit the demo user's videos.
    if email_owner is not None and email_owner.id != (user.id if user else None):
        raise ApiError("该邮箱已关联其他本地账号，请联系管理员迁移数据", status.HTTP_409_CONFLICT)

    if user is None:
        user = User(
            email=email,
            password_hash="supabase-managed",
            auth_subject=auth_subject,
            display_name=display_name,
            avatar_url=avatar_url,
        )
        db.add(user)
    else:
        user.email = email
        user.display_name = display_name or user.display_name
        user.avatar_url = avatar_url or user.avatar_url

    db.commit()
    db.refresh(user)
    return user
