"""Read-only, identity-free queue summary for operator checks."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from app.models.video_task import VideoTask


def task_queue_snapshot(db: Session, *, now: datetime | None = None) -> dict[str, int | str]:
    if db.new or db.dirty or db.deleted:
        raise ValueError('Queue monitoring requires a clean dedicated session')
    db.rollback()
    try:
        if db.bind.dialect.name == 'postgresql':
            db.connection().exec_driver_sql('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
            db.execute(text('SET LOCAL search_path = pg_catalog, public'))
            if db.scalar(text("SELECT row_security_active('public.video_tasks'::regclass)")):
                raise ValueError('Queue monitoring requires an unfiltered backend view')
        return _snapshot(db, now=now)
    finally:
        db.rollback()


def _snapshot(db, *, now):
    now = now or datetime.now(UTC)
    counts = dict(db.execute(select(VideoTask.status, func.count()).group_by(VideoTask.status)).all())
    oldest_queued = db.scalar(select(func.min(VideoTask.created_at)).where(VideoTask.status == "queued"))
    if oldest_queued is not None and oldest_queued.tzinfo is None:
        oldest_queued = oldest_queued.replace(tzinfo=UTC)
    expired_leases = db.scalar(select(func.count()).select_from(VideoTask).where(
        VideoTask.status == "running", VideoTask.lease_expires_at <= now,
    )) or 0
    invalid_leases = db.scalar(select(func.count()).select_from(VideoTask).where(
        VideoTask.status == 'running', or_(VideoTask.lease_expires_at.is_(None),
                                         VideoTask.worker_id.is_(None), func.trim(VideoTask.worker_id) == ''),
    )) or 0
    known = ('queued', 'running', 'succeeded', 'failed', 'cancelled')
    recent_failures = db.scalar(select(func.count()).select_from(VideoTask).where(
        VideoTask.status == "failed", VideoTask.finished_at >= now - timedelta(hours=1),
    )) or 0
    return {
        "checked_at": now.isoformat(),
        "queued": counts.get("queued", 0),
        "running": counts.get("running", 0),
        "succeeded": counts.get("succeeded", 0),
        "failed": counts.get("failed", 0),
        "cancelled": counts.get("cancelled", 0),
        "oldest_queued_seconds": max(0, int((now - oldest_queued).total_seconds())) if oldest_queued else 0,
        "expired_leases": expired_leases,
        "failed_last_hour": recent_failures,
        "invalid_running_leases": invalid_leases,
        "unknown_status_tasks": sum(count for state, count in counts.items() if state not in known),
    }
