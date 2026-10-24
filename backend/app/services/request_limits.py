"""Database-backed rate limits shared by all API instances."""

from datetime import UTC, datetime, timedelta

from fastapi import status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models.request_window import RequestWindow
from app.models.user import User


WINDOW = timedelta(minutes=1)


def lock_user_for_limits(db: Session, user_id: str) -> None:
    """Serialize one user's admissions before reading counters or active tasks."""
    db.execute(select(User.id).where(User.id == user_id).with_for_update()).scalar_one()


def consume_request(db: Session, user_id: str, action: str, limit: int, *, now: datetime | None = None) -> None:
    """Reserve one request in the current transaction; caller holds the user row lock."""
    current = now or datetime.now(UTC)
    window = db.get(RequestWindow, (user_id, action))
    if window is None:
        db.add(RequestWindow(user_id=user_id, action=action, window_started_at=current, request_count=1))
        return
    start = window.window_started_at
    if start.tzinfo is None:
        start = start.replace(tzinfo=UTC)
    if current >= start + WINDOW:
        window.window_started_at = current
        window.request_count = 1
    elif window.request_count >= limit:
        db.rollback()
        raise ApiError(f"请求过于频繁，每分钟最多 {limit} 次，请稍后再试", status.HTTP_429_TOO_MANY_REQUESTS)
    else:
        window.request_count += 1
