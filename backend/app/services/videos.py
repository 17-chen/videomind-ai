from fastapi import status
from sqlalchemy import Select, func, or_, select, update
from sqlalchemy.orm import Session, joinedload

from app.core.errors import ApiError
from app.core.i18n import t
from app.models.summary import Summary
from app.models.user import User
from app.models.video import Video, VideoStatus
from app.schemas.video import VideoCreate


def create_video(db: Session, user: User, payload: VideoCreate) -> Video:
    video = Video(
        user_id=user.id,
        url=str(payload.url),
        title=payload.title,
        description=payload.description,
        status=VideoStatus.CREATED.value,
        source=detect_video_source(str(payload.url)),
        tags=payload.tags,
    )
    db.add(video)
    db.commit()
    db.refresh(video)
    return video


ACTIVE_VIDEO_STATUSES = (
    VideoStatus.PROCESSING.value,
    VideoStatus.DOWNLOADING.value,
    VideoStatus.TRANSCRIBING.value,
    VideoStatus.ANALYZING.value,
    VideoStatus.EMBEDDING.value,
)


def claim_video_operation(db: Session, video: Video, next_status: VideoStatus) -> Video:
    """Atomically claim a video so duplicate requests cannot start concurrent jobs."""
    result = db.execute(
        update(Video)
        .where(Video.id == video.id, Video.user_id == video.user_id, Video.status.not_in(ACTIVE_VIDEO_STATUSES))
        .values(status=next_status.value, processing_error=None)
    )
    if result.rowcount != 1:
        db.rollback()
        raise ApiError(t("video_already_processing"), status_code=status.HTTP_409_CONFLICT)
    db.commit()
    db.refresh(video)
    return video


def mark_video_processing(db: Session, video: Video) -> Video:
    return claim_video_operation(db, video, VideoStatus.DOWNLOADING)


def update_video_status(
    db: Session,
    video: Video,
    video_status: VideoStatus,
    processing_error: str | None = None,
) -> Video:
    video.status = video_status.value
    video.processing_error = processing_error[:4000] if processing_error else None
    db.add(video)
    db.commit()
    db.refresh(video)
    return video


def list_videos_for_user(
    db: Session,
    user: User,
    limit: int,
    offset: int,
    search: str | None = None,
    category: str | None = None,
) -> tuple[list[Video], int]:
    statement = _base_video_query(user.id)

    if search:
        pattern = f"%{search}%"
        statement = statement.where(or_(Video.title.ilike(pattern), Video.description.ilike(pattern), Video.url.ilike(pattern)))

    if category:
        statement = statement.join(Summary, Summary.video_id == Video.id).where(Summary.category == category)

    total_statement = select(func.count()).select_from(statement.subquery())
    total = db.scalar(total_statement) or 0

    videos = list(
        db.scalars(
            statement.order_by(Video.created_at.desc())
            .offset(offset)
            .limit(limit)
            .options(joinedload(Video.transcript), joinedload(Video.summary))
        ).unique()
    )
    return videos, total


def get_video_for_user(db: Session, user: User, video_id: str) -> Video:
    video = db.scalar(
        _base_video_query(user.id)
        .where(Video.id == video_id)
        .options(joinedload(Video.transcript), joinedload(Video.summary), joinedload(Video.embedding))
    )
    if video is None:
        raise ApiError(t("video_not_found"), status_code=status.HTTP_404_NOT_FOUND)
    return video


def detect_video_source(url: str) -> str | None:
    lowered_url = url.lower()
    if "bilibili.com" in lowered_url or "b23.tv" in lowered_url:
        return "bilibili"
    if "douyin.com" in lowered_url:
        return "douyin"
    if "youtube.com" in lowered_url or "youtu.be" in lowered_url:
        return "youtube"
    if "tiktok.com" in lowered_url:
        return "tiktok"
    return None


def _base_video_query(user_id: str) -> Select[tuple[Video]]:
    return select(Video).where(Video.user_id == user_id)
