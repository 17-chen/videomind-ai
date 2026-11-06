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
from app.services.storage_quota import STORAGE_LIMIT_MESSAGE, user_storage_bytes
from app.services.temporary_storage import STAGE_LIMIT_MESSAGE, stage_limit_bytes


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
    return publish_artifacts(db, user_id=user_id, video_id=video_id, kind=kind, paths=[path], store=store)[0]


def publish_artifacts(db: Session, *, user_id: str, video_id: str, kind: str, paths: list[Path], store,
                      replace_kind: bool = False, on_publish=None) -> list[ArtifactSpec]:
    """Publish one bounded group atomically; requires a clean dedicated Session.

    replace_kind=True treats the files as a complete snapshot (e.g. video plus
    subtitles), retiring names absent from the new output. Network outcomes and
    failed SQL publication retain all pending keys and the previous ready group.
    """
    if db.new or db.dirty or db.deleted:
        raise ValueError('Object publication requires a clean dedicated database session')
    if not 1 <= len(paths) <= 100 or len({path.name for path in paths}) != len(paths):
        raise ValueError('A group requires 1-100 distinct artifact filenames')
    try:
        _owned_video(db, user_id, video_id)
        if user_storage_bytes(db, user_id):
            raise ApiError(UNAVAILABLE, 503)
        specs = []
        size = 0
        for path in paths:
            count, checksum = measure_file(path)
            size += count
            if size > stage_limit_bytes():
                raise ApiError(STAGE_LIMIT_MESSAGE, 413)
            specs.append(ArtifactSpec(id=str(uuid4()), user_id=user_id, video_id=video_id, kind=kind, filename=path.name,
                                      bucket=store.bucket, project_fingerprint=store.project_fingerprint, sha256=checksum, size_bytes=count))
        # Register ALL keys before releasing the video lock and starting remote I/O.
        _owned_video(db, user_id, video_id, lock=True)
        rows = [StoredArtifact(**{name: getattr(spec, name) for name in SPEC_FIELDS}, state='pending') for spec in specs]
        db.add_all(rows)
        db.commit()
        for spec, path in zip(specs, paths, strict=True):
            store.put(spec, path)
        if db.scalar(select(User.id).where(User.id == user_id).with_for_update()) is None:
            raise ApiError('未找到该视频', 404)
        if user_storage_bytes(db, user_id):  # Recheck under the user lock against a concurrent local admission.
            raise ApiError(UNAVAILABLE, 503)
        _owned_video(db, user_id, video_id, lock=True)
        for row in rows:
            db.refresh(row, with_for_update=True)
            if row.delete_requested or row.state != 'pending':
                raise ApiError('未找到该文件', 404)
        previous_query = select(StoredArtifact).where(
            StoredArtifact.user_id == user_id, StoredArtifact.video_id == video_id,
            StoredArtifact.kind == kind, StoredArtifact.state == 'ready',
        )
        if not replace_kind:
            previous_query = previous_query.where(StoredArtifact.filename.in_([spec.filename for spec in specs]))
        previous = db.scalars(previous_query.order_by(StoredArtifact.id).with_for_update()).all()
        used = db.scalar(select(func.coalesce(func.sum(StoredArtifact.size_bytes), 0)).where(
            StoredArtifact.user_id == user_id, StoredArtifact.state == 'ready',
        ))
        replaced = sum(row.size_bytes for row in previous)
        if size > replaced and used - replaced + size > settings.max_user_storage_mb * 1024 * 1024:
            raise ApiError(STORAGE_LIMIT_MESSAGE, 413)
        for row in previous:
            row.state = 'retired'
        db.flush()  # Free partial unique slots in the SAME transaction as publishing all new rows.
        for row in rows:
            row.state = 'ready'
        if on_publish is not None:
            on_publish(specs)  # SQL-only callback; commits with the entire ready group.
        db.commit()
        return specs
    except SQLAlchemyError as exc:
        db.rollback()
        logger.error('Object ledger publication error type={}', type(exc).__name__)
        raise ApiError(UNAVAILABLE, 503) from None
    except Exception:
        db.rollback()
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


@contextmanager
def materialize_artifacts(db: Session, *, user_id: str, video_id: str, kind: str, cache_root: Path, store, required_id: str):
    _owned_video(db, user_id, video_id)
    rows = db.scalars(select(StoredArtifact).where(
        StoredArtifact.user_id == user_id, StoredArtifact.video_id == video_id, StoredArtifact.kind == kind,
        StoredArtifact.state == 'ready', StoredArtifact.delete_requested.is_(False),
    ).order_by(StoredArtifact.filename)).all()
    specs = [spec_for(row) for row in rows]
    if required_id not in {spec.id for spec in specs}:
        raise ApiError('未找到该文件', 404)
    if len(specs) > 100 or sum(spec.size_bytes for spec in specs) > stage_limit_bytes():
        raise ApiError(STAGE_LIMIT_MESSAGE, 413)
    cache_root.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='.object-group-', dir=cache_root) as directory:
        root = Path(directory)
        files = {}
        for spec in specs:
            path = root / spec.filename
            store.download(spec, path)
            files[spec.id] = path
        _owned_video(db, user_id, video_id)  # Do not release plaintext after a concurrent video deletion.
        yield root, files[required_id]
