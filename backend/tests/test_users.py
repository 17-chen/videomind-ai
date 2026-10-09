import pytest
from fastapi import status
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.errors import ApiError
from app.database.base import Base
from app.models import User
from app.services.users import get_or_create_authenticated_user


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def test_authenticated_user_is_reused_by_subject(db: Session) -> None:
    first = get_or_create_authenticated_user(db, auth_subject="auth-1", email="first@example.com")
    second = get_or_create_authenticated_user(db, auth_subject="auth-1", email="new@example.com")
    assert first.id == second.id
    assert second.email == "new@example.com"


def test_signup_cannot_claim_existing_email_and_videos(db: Session) -> None:
    existing = User(email="demo@example.com", password_hash="local")
    db.add(existing)
    db.commit()
    with pytest.raises(ApiError) as error:
        get_or_create_authenticated_user(db, auth_subject="new-auth-user", email="demo@example.com")
    assert error.value.status_code == status.HTTP_409_CONFLICT
    assert existing.auth_subject is None


def test_video_query_is_scoped_to_authenticated_user(db: Session) -> None:
    from app.models import Video
    from app.services.videos import get_video_for_user

    owner = get_or_create_authenticated_user(db, auth_subject="auth-owner", email="owner@example.com")
    other = get_or_create_authenticated_user(db, auth_subject="auth-other", email="other@example.com")
    video = Video(user_id=owner.id, url="https://www.bilibili.com/video/BV1example")
    db.add(video)
    db.commit()

    with pytest.raises(ApiError) as error:
        get_video_for_user(db, other, video.id)
    assert error.value.status_code == status.HTTP_404_NOT_FOUND
