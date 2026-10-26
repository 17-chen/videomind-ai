"""Read-only, identity-free queue summary for operator checks."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.video_task import VideoTask


def task_queue_snapshot(db: Session, *, now: datetime | None = None) -> dict[str, int | str]:
    now = now or datetime.now(UTC)
    counts = dict(db.execute(select(VideoTask.status, func.count()).group_by(VideoTask.status)).all())
    oldest_queued = db.scalar(select(func.min(VideoTask.created_at)).where(VideoTask.status == "queued"))
    if oldest_queued is not None and oldest_queued.tzinfo is None:
        oldest_queued = oldest_queued.replace(tzinfo=UTC)
    expired_leases = db.scalar(select(func.count()).select_from(VideoTask).where(
        VideoTask.status == "running", VideoTask.lease_expires_at < now,
    )) or 0
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
    }
