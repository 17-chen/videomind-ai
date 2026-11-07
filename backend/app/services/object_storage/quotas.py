"""Logical ready bytes plus durable uncertain source-upload reservations."""

from sqlalchemy import exists, func, literal, or_, select

from app.core.config import settings
from app.core.errors import ApiError
from app.models import Video
from app.services.object_storage.models import StoredArtifact
from app.services.object_storage.references import PREFIX
from app.services.object_storage.spec import UNAVAILABLE
from app.services.storage_quota import STORAGE_LIMIT_MESSAGE, user_storage_bytes

SOURCE_LIMIT = '已达到个人上传视频存储上限，请先删除不需要的视频'
UPLOAD_UNCERTAIN = '相同视频正在上传或等待核对，请稍后重试'


def logical_bytes(db, user_id):
    return db.scalar(select(func.coalesce(func.sum(StoredArtifact.size_bytes), 0)).where(
        StoredArtifact.user_id == user_id,
        or_(StoredArtifact.state == 'ready', StoredArtifact.is_source_upload.is_(True) & (StoredArtifact.state == 'pending')),
    ))


def check_source_admission(db, *, user_id, checksum, incoming_bytes=0, exclude_id=None):
    """Caller holds the user lock. The final check includes its own reservation."""
    valid_source = exists(select(StoredArtifact.id).where(
        StoredArtifact.user_id == Video.user_id, StoredArtifact.video_id == Video.id,
        Video.media_path == literal(PREFIX) + StoredArtifact.id,
        StoredArtifact.is_source_upload.is_(True), StoredArtifact.state == 'ready',
    ))
    if user_storage_bytes(db, user_id) or db.scalar(select(Video.id).where(
        Video.user_id == user_id, Video.source == 'upload', ~valid_source,
    ).limit(1)):
        raise ApiError(UNAVAILABLE, 503)
    if db.scalar(select(Video.id).where(Video.user_id == user_id, Video.upload_sha256 == checksum).limit(1)):
        raise ApiError('你已经上传过这个视频', 409)
    duplicate = select(StoredArtifact.id).where(
        StoredArtifact.user_id == user_id, StoredArtifact.is_source_upload.is_(True),
        StoredArtifact.sha256 == checksum, StoredArtifact.state == 'pending',
    )
    if exclude_id is not None:
        duplicate = duplicate.where(StoredArtifact.id != exclude_id)
    if db.scalar(duplicate.limit(1)):
        raise ApiError(UPLOAD_UNCERTAIN, 409)
    source_bytes = db.scalar(select(func.coalesce(func.sum(StoredArtifact.size_bytes), 0)).where(
        StoredArtifact.user_id == user_id, StoredArtifact.is_source_upload.is_(True), StoredArtifact.state.in_(('ready', 'pending')),
    ))
    if source_bytes + incoming_bytes > settings.max_user_upload_mb * 1024 * 1024:
        raise ApiError(SOURCE_LIMIT, 413)
    if logical_bytes(db, user_id) + incoming_bytes > settings.max_user_storage_mb * 1024 * 1024:
        raise ApiError(STORAGE_LIMIT_MESSAGE, 413)
