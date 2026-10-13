from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database.base import Base
from app.models import AiSettings, Embedding, Summary, Transcript, User, Video  # noqa: F401
from app.models.video import VideoStatus
from app.services.videos import recover_interrupted_videos


def test_recovery_only_releases_interrupted_tasks():
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            user = User(email="owner@example.com", password_hash="demo")
            active = Video(user=user, url="https://example.com/active", status=VideoStatus.DOWNLOADING.value, tags=[])
            complete = Video(user=user, url="https://example.com/done", status=VideoStatus.COMPLETED.value, tags=[])
            db.add_all([active, complete])
            db.commit()

            assert recover_interrupted_videos(db) == 1
            db.refresh(active)
            db.refresh(complete)
            assert active.status == VideoStatus.FAILED.value
            assert "重试" in active.processing_error
            assert complete.status == VideoStatus.COMPLETED.value
            assert recover_interrupted_videos(db) == 0
    finally:
        engine.dispose()
