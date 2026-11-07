"""Durable source-upload reservation, remote transfer, then atomic visibility."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.errors import ApiError
from app.core.logging import logger
from app.models import User, Video
from app.services.object_storage.models import StoredArtifact
from app.services.object_storage.quotas import check_source_admission, UPLOAD_UNCERTAIN
from app.services.object_storage.references import artifact_reference
from app.services.object_storage.repository import SPEC_FIELDS
from app.services.object_storage.spec import ArtifactSpec, UNAVAILABLE


def publish_uploaded_video(db, *, user_id, video_id, path, size, checksum, duration, title, store):
    """Clean dedicated Session; API failure may leave a counted pending intent.

    No Video exists until the acknowledged upload and reservation commit together.
    Unknown outcomes are never undone by deleting the remote key or its ledger.
    """
    if db.new or db.dirty or db.deleted:
        raise ValueError('Object upload requires a clean dedicated database session')
    spec = ArtifactSpec(id=video_id, user_id=user_id, video_id=video_id, kind='video', filename=path.name,
                        bucket=store.bucket, project_fingerprint=store.project_fingerprint, sha256=checksum, size_bytes=size)
    try:
        if db.scalar(select(User.id).where(User.id == user_id).with_for_update()) is None:
            raise ApiError('未找到该用户', 404)
        check_source_admission(db, user_id=user_id, checksum=checksum, incoming_bytes=size)
        row = StoredArtifact(**{name: getattr(spec, name) for name in SPEC_FIELDS}, state='pending', is_source_upload=True)
        db.add(row)
        db.commit()  # Source quota and immutable key survive a lost upload response.
        store.put(spec, path)  # No user/video SQL lock is held during transfer.
        if db.scalar(select(User.id).where(User.id == user_id).with_for_update()) is None:
            raise ApiError('未找到该用户', 404)
        db.refresh(row, with_for_update=True)
        if row.state != 'pending' or row.delete_requested or not row.is_source_upload:
            raise ApiError(UNAVAILABLE, 503)
        check_source_admission(db, user_id=user_id, checksum=checksum, exclude_id=row.id)
        video = Video(id=video_id, user_id=user_id, url=f'upload://{video_id}', title=title,
                      duration=duration, status='created', source='upload', tags=[],
                      media_path=artifact_reference(spec.id), upload_sha256=checksum)
        db.add(video)
        row.state = 'ready'
        db.commit()
        db.refresh(video)
        return video
    except IntegrityError as exc:
        db.rollback()
        constraint = getattr(getattr(exc.orig, 'diag', None), 'constraint_name', None)
        if constraint == 'uq_videos_user_upload_sha256':
            raise ApiError('你已经上传过这个视频', 409) from None
        if constraint == 'uq_storage_pending_upload':
            raise ApiError(UPLOAD_UNCERTAIN, 409) from None
        logger.warning('Object upload database error type={}', type(exc).__name__)
        raise ApiError(UNAVAILABLE, 503) from None
    except SQLAlchemyError as exc:
        db.rollback()
        logger.warning('Object upload database error type={}', type(exc).__name__)
        raise ApiError(UNAVAILABLE, 503) from None
    except Exception:
        db.rollback()
        raise
