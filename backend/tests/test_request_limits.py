from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.errors import ApiError
from app.database.base import Base
from app.models import RequestWindow, User  # noqa: F401
from app.services.request_limits import consume_request, lock_user_for_limits


def test_request_window_resets_at_one_minute_and_keeps_actions_separate():
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    start = datetime(2026, 10, 24, tzinfo=UTC)
    try:
        with Session(engine) as db:
            user = User(email="rate-test@example.com", password_hash="test")
            db.add(user)
            db.commit()
            user_id = user.id
            lock_user_for_limits(db, user_id)
            consume_request(db, user_id, "chat", 1, now=start)
            consume_request(db, user_id, "video_task", 1, now=start)
            db.commit()

            lock_user_for_limits(db, user_id)
            with pytest.raises(ApiError) as exc:
                consume_request(db, user_id, "chat", 1, now=start + timedelta(seconds=59))
            assert exc.value.status_code == 429

            lock_user_for_limits(db, user_id)
            consume_request(db, user_id, "chat", 1, now=start + timedelta(seconds=60))
            db.commit()
            window = db.get(RequestWindow, (user_id, "chat"))
            assert window.request_count == 1
            assert window.window_started_at.replace(tzinfo=UTC) == start + timedelta(seconds=60)
            assert db.get(RequestWindow, (user_id, "video_task")).request_count == 1
    finally:
        engine.dispose()
