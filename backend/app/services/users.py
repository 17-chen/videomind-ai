from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
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
