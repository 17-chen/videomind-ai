"""Explicit object publication: durable pending record, upload, atomic pointer switch.

Not wired to the local pipeline yet. Never treat local quotas or paths as remote
truth until upload/read/delete flows have migrated together.
"""

from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.errors import ApiError
from app.core.logging import logger
from app.models import User, Video
from app.services.object_storage.models import StoredArtifact
from app.services.object_storage.spec import ArtifactSpec, UNAVAILABLE, measure_file
from app.services.storage_quota import STORAGE_LIMIT_MESSAGE


SPEC_FIELDS = tuple(ArtifactSpec.__dataclass_fields__)


def spec_for(row: StoredArtifact) -> ArtifactSpec:
    return ArtifactSpec(**{name: getattr(row, name) for name in SPEC_FIELDS})


def _owned_video(db: Session, user_id: str, video_id: str, *, lock=False):
    query = select(Video).where(Video.id == video_id, Video.user_id == user_id)
    if lock:
        query = query.with_for_update()
    video = db.scalar(query)
    if video is None:
        raise ApiError('未找到该视频', 404)
    return video


def _owned_artifact(db: Session, user_id: str, artifact_id: str, states):
    row = db.scalar(select(StoredArtifact).where(StoredArtifact.id == artifact_id, StoredArtifact.user_id == user_id, StoredArtifact.state.in_(states)))
    if row is None:
        raise ApiError('未找到该文件', 404)
    _owned_video(db, user_id, row.video_id)
    return row


def publish_artifact(db: Session, *, user_id: str, video_id: str, kind: str, path: Path, store) -> ArtifactSpec:
    """Requires a dedicated Session: commits the pending intent before remote I/O."""
    if db.new or db.dirty or db.deleted:
        raise ValueError('Object publication requires a clean dedicated database session')
    try:
        _owned_video(db, user_id, video_id)
        size, checksum = measure_file(path)
        spec = ArtifactSpec(id=str(uuid4()), user_id=user_id, video_id=video_id, kind=kind, filename=path.name,
                            bucket=store.bucket, project_fingerprint=store.project_fingerprint, sha256=checksum, size_bytes=size)
        # Register the immutable key before deletion can remove the video. The
        # lock ends at the pending commit, BEFORE any remote transfer begins.
        _owned_video(db, user_id, video_id, lock=True)
        row = StoredArtifact(**{name: getattr(spec, name) for name in SPEC_FIELDS}, state='pending')
        db.add(row)
        db.commit()  # Record the immutable key before an upload with unknown outcome.
        store.put(spec, path)
        if db.scalar(select(User.id).where(User.id == user_id).with_for_update()) is None:
            raise ApiError('未找到该视频', 404)
        _owned_video(db, user_id, video_id, lock=True)
        db.refresh(row, with_for_update=True)
        if row.delete_requested or row.state != 'pending':
            raise ApiError('未找到该文件', 404)
        previous = db.scalar(select(StoredArtifact).where(
            StoredArtifact.user_id == user_id, StoredArtifact.video_id == video_id,
            StoredArtifact.kind == kind, StoredArtifact.filename == path.name, StoredArtifact.state == 'ready',
        ).with_for_update())
        used = db.scalar(select(func.coalesce(func.sum(StoredArtifact.size_bytes), 0)).where(
            StoredArtifact.user_id == user_id, StoredArtifact.state == 'ready',
        ))
        replaced = previous.size_bytes if previous else 0
        if size > replaced and used - replaced + size > settings.max_user_storage_mb * 1024 * 1024:
            raise ApiError(STORAGE_LIMIT_MESSAGE, 413)
        if previous:
            previous.state = 'retired'
            db.flush()  # Release the partial unique ready slot within this transaction.
        row.state = 'ready'
        db.commit()
        return spec
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error('Object ledger publication error type={}', type(exc).__name__)
        raise ApiError(UNAVAILABLE, 503) from None
    except Exception:
        db.rollback()
        # Retain pending intent and any remote object. Never delete a key whose
        # publication outcome could be ambiguous after a transport/commit failure.
        raise


@contextmanager
def materialize_artifact(db: Session, *, user_id: str, artifact_id: str, cache_root: Path, store):
    row = _owned_artifact(db, user_id, artifact_id, ('ready',))
    spec = spec_for(row)
    cache_root.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='.object-read-', dir=cache_root) as directory:
        path = Path(directory) / spec.filename
        store.download(spec, path)
        yield path


def retire_artifact(db: Session, *, user_id: str, artifact_id: str):
    row = _owned_artifact(db, user_id, artifact_id, ('ready', 'retired'))
    # Serialize against other operations on this exact ledger entry.
    db.refresh(row, with_for_update=True)
    if row.state not in ('ready', 'retired'):
        raise ApiError('未找到该文件', 404)
    row.state = 'retired'
    db.commit()


def purge_retired_artifact(db: Session, *, user_id: str, artifact_id: str, store):
    row = _owned_artifact(db, user_id, artifact_id, ('retired', 'deleted'))
    if row.state == 'deleted':
        return
    spec = spec_for(row)
    store.delete(spec)
    db.refresh(row, with_for_update=True)
    if row.state != 'retired':
        db.rollback()
        raise ApiError(UNAVAILABLE, 503)
    row.state = 'deleted'
    db.commit()
