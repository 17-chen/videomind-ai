"""Explicit deletion intent, committed with the business delete; bounded recovery.

Only confirmed uploads (retired) are eligible. Pending uploads are never inferred
safe to delete from their age, a 404, or the absence of their video.
"""

from sqlalchemy import exists, func, inspect, select
from sqlalchemy.orm import Session

from app.core.logging import logger
from app.models import Video
from app.services.object_storage.models import StoredArtifact
from app.services.object_storage.repository import spec_for


def ledger_installed(db: Session) -> bool:
    connection = db.connection()
    schema = 'public' if connection.dialect.name == 'postgresql' else None
    return inspect(connection).has_table(StoredArtifact.__tablename__, schema=schema)


def stage_video_deletion(db: Session, video: Video) -> None:
    """Caller must hold the owned video lock, and commit with db.delete(video).

    Missing optional table preserves the local-only workflow. An outdated or
    inaccessible ledger raises BEFORE deleting vectors or the business record.
    """
    if not ledger_installed(db):
        return
    rows = db.scalars(select(StoredArtifact).where(
        StoredArtifact.user_id == video.user_id, StoredArtifact.video_id == video.id,
        StoredArtifact.state != 'deleted',
    ).with_for_update()).all()
    for row in rows:
        row.delete_requested = True
        if row.state == 'ready':
            row.state = 'retired'
    db.flush()


def _requested():
    return StoredArtifact.delete_requested.is_(True)


def _video_exists():
    # Any video with this ID blocks physical deletion, including after a manual restore.
    return exists(select(Video.id).where(Video.id == StoredArtifact.video_id))


def _eligible():
    return _requested() & (StoredArtifact.state == 'retired') & ~_video_exists()


def cleanup_snapshot(db: Session) -> dict:
    if not ledger_installed(db):
        return {'status': 'not_installed', 'eligible': 0, 'pending_uncertain': 0, 'blocked': 0}

    def count(condition):
        return db.scalar(select(func.count()).select_from(StoredArtifact).where(condition))

    return {
        'status': 'preview',
        'eligible': count(_eligible()),
        'pending_uncertain': count(_requested() & (StoredArtifact.state == 'pending')),
        'blocked': count(_requested() & (StoredArtifact.state != 'deleted') & (
            _video_exists() | (StoredArtifact.state == 'ready')
        )),
    }


def cleanup_requested_objects(db: Session, *, store, limit: int = 20) -> dict:
    """Trusted maintenance entrypoint; NOT a user API. Store verifies project/bucket.

    Row locks serialize cleanup attempts, not video/user processing; no business
    locks are held during remote I/O. Retry only exact immutable keys. PostgreSQL
    SKIP LOCKED permits multiple maintenance workers; SQLite is test-only here.
    """
    if not 1 <= limit <= 100:
        raise ValueError('Cleanup limit must be between 1 and 100')
    if db.new or db.dirty or db.deleted:
        raise ValueError('Object cleanup requires a clean dedicated database session')
    initial = cleanup_snapshot(db)
    result = {'attempted': 0, 'confirmed_deleted': 0, 'failed': 0}
    if initial['status'] == 'not_installed':
        return {**initial, **result}
    db.rollback()  # Finish the read-only snapshot before individual recovery transactions.
    seen = []
    for _ in range(limit):
        row = db.scalar(select(StoredArtifact).where(_eligible(), StoredArtifact.id.not_in(seen))
                        .order_by(StoredArtifact.id).limit(1).with_for_update(skip_locked=True))
        if row is None:
            db.rollback()
            break
        seen.append(row.id)
        result['attempted'] += 1
        try:
            store.delete(spec_for(row))  # Must confirm absence, not only acknowledge DELETE.
            row.state = 'deleted'
            db.commit()
            result['confirmed_deleted'] += 1
        except Exception as exc:
            db.rollback()  # Keep the intent for a later explicit retry, even after DELETE.
            result['failed'] += 1
            logger.warning('Object cleanup failure type={}', type(exc).__name__)
    report = {**cleanup_snapshot(db), **result}
    report['status'] = 'complete' if not any(report[name] for name in ('eligible', 'pending_uncertain', 'blocked', 'failed')) else 'needs_attention'
    return report
