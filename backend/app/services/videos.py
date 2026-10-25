from pathlib import Path

from fastapi import status
from sqlalchemy import Select, func, or_, select, update
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.core.errors import ApiError
from app.core.logging import logger
from app.core.i18n import t
from app.models.summary import Summary
from app.models.user import User
from app.models.video import Video, VideoStatus
from app.models.video_task import VideoTask
from app.schemas.video import VideoCreate, VideoNoteUpdate, VideoUpdate
from app.services.analysis import _persist_markdown_note
from app.services.rag import index_video
from app.services.vector_store import vector_store


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
    VideoStatus.QUEUED.value,
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
    return claim_video_operation(db, video, VideoStatus.TRANSCRIBING if video.source == "upload" else VideoStatus.DOWNLOADING)


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


def recover_interrupted_videos(db: Session) -> int:
    """Release tasks abandoned by a stopped single-process local server."""
    result = db.execute(
        update(Video)
        .where(Video.status.in_(ACTIVE_VIDEO_STATUSES), ~Video.tasks.any(VideoTask.status.in_(("queued", "running"))))
        .values(
            status=VideoStatus.FAILED.value,
            processing_error="服务重启中断了处理，请点击重试",
        )
    )
    db.commit()
    return result.rowcount or 0


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
        statement = statement.where(or_(
            Video.title.icontains(search, autoescape=True),
            Video.description.icontains(search, autoescape=True),
            Video.url.icontains(search, autoescape=True),
            Video.summary.has(or_(
                Summary.title.icontains(search, autoescape=True),
                Summary.summary.icontains(search, autoescape=True),
            )),
        ))

    if category:
        statement = statement.outerjoin(Summary, Summary.video_id == Video.id).where(
            func.coalesce(Video.user_category, Summary.category) == category
        )

    total_statement = select(func.count()).select_from(statement.subquery())
    total = db.scalar(total_statement) or 0

    videos = list(
        db.scalars(
            statement.order_by(Video.created_at.desc(), Video.id.desc())
            .offset(offset)
            .limit(limit)
            .options(joinedload(Video.transcript), joinedload(Video.summary))
        ).unique()
    )
    return videos, total


def list_video_categories_for_user(db: Session, user: User) -> list[str]:
    effective_category = func.coalesce(Video.user_category, Summary.category)
    return list(db.scalars(
        select(effective_category)
        .select_from(Video)
        .outerjoin(Summary, Summary.video_id == Video.id)
        .where(Video.user_id == user.id, effective_category.is_not(None), effective_category != "")
        .distinct()
        .order_by(effective_category)
    ))


def update_video_for_user(db: Session, user: User, video_id: str, payload: VideoUpdate) -> Video:
    video = get_video_for_user(db, user, video_id)
    _ensure_editable(video)
    changes = payload.model_dump(exclude_unset=True)
    if "title" in changes:
        video.title = (changes["title"] or "").strip() or None
    if "description" in changes:
        video.description = (changes["description"] or "").strip() or None
    if "tags" in changes:
        video.tags = [tag.strip() for tag in (changes["tags"] or [])]
    if "category" in changes:
        video.user_category = (changes["category"] or "").strip() or None
    _commit_and_sync(db, video)
    return video


def update_note_for_user(db: Session, user: User, video_id: str, payload: VideoNoteUpdate) -> Video:
    video = get_video_for_user(db, user, video_id)
    _ensure_editable(video)
    if video.summary is None:
        raise ApiError("请先完成 AI 分析，再编辑笔记", status_code=status.HTTP_409_CONFLICT)
    video.summary.markdown_note = payload.markdown_note
    video.summary.note_is_manual = True
    _persist_markdown_note(video.id, payload.markdown_note)
    _commit_and_sync(db, video)
    return video


def sync_video_index_for_user(db: Session, user: User, video_id: str) -> Video:
    video = get_video_for_user(db, user, video_id)
    _ensure_editable(video)
    if video.embedding is None:
        raise ApiError("视频尚未写入知识库", status_code=status.HTTP_409_CONFLICT)
    _sync_index(db, video)
    return video


def _ensure_editable(video: Video) -> None:
    if video.status in ACTIVE_VIDEO_STATUSES:
        raise ApiError(t("video_already_processing"), status_code=status.HTTP_409_CONFLICT)


def _commit_and_sync(db: Session, video: Video) -> None:
    if video.embedding is not None:
        video.index_sync_error = "知识库内容待同步"
    db.commit()
    if video.embedding is not None:
        _sync_index(db, video)


def _sync_index(db: Session, video: Video) -> None:
    try:
        index_video(db, video)
    except Exception as exc:
        db.rollback()
        logger.warning("Index sync failed for video {}: {}", video.id, type(exc).__name__)
        video.index_sync_error = "知识库同步失败，请重试"
        db.commit()


def get_video_for_user(db: Session, user: User, video_id: str) -> Video:
    video = db.scalar(
        _base_video_query(user.id)
        .where(Video.id == video_id)
        .options(joinedload(Video.transcript), joinedload(Video.summary), joinedload(Video.embedding))
    )
    if video is None:
        raise ApiError(t("video_not_found"), status_code=status.HTTP_404_NOT_FOUND)
    return video


def delete_video_for_user(db: Session, user: User, video_id: str) -> None:
    video = db.scalar(
        _base_video_query(user.id).where(Video.id == video_id).with_for_update()
    )
    if video is None:
        raise ApiError(t("video_not_found"), status_code=status.HTTP_404_NOT_FOUND)
    if video.status in ACTIVE_VIDEO_STATUSES:
        raise ApiError(t("video_already_processing"), status_code=status.HTTP_409_CONFLICT)

    # Keep the database row until the user's Chroma entry has been removed.
    # The vector ID is deterministic, so this also cleans up an index whose DB write failed.
    vector_store.delete_video_document(vector_id=f"video:{video.id}", user_id=user.id)
    db.delete(video)
    db.commit()
    _cleanup_video_files(video_id)


def _cleanup_video_files(video_id: str) -> None:
    # Only touch files named from our generated video ID inside configured storage roots.
    for directory in (
        settings.video_storage_dir,
        settings.audio_storage_dir,
        settings.transcript_storage_dir,
        settings.note_storage_dir,
    ):
        for path in Path(directory).glob(f"{video_id}.*"):
            if path.is_file() or path.is_symlink():
                try:
                    path.unlink()
                except OSError as exc:
                    logger.warning("Could not remove generated file for video {}: {}", video_id, type(exc).__name__)


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
