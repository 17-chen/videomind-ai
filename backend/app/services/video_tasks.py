"""PostgreSQL-backed video work queue and cooperative cancellation."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi import status
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ApiError
from app.core.i18n import t
from app.core.logging import logger
from app.models.user import User
from app.models.video import Video, VideoStatus
from app.models.video_task import VideoTask
from app.services.analysis import analyze_video
from app.services.rag import index_video
from app.services.request_limits import lock_user_for_limits
from app.services.video_processing.pipeline import process_video
from app.services.videos import ACTIVE_VIDEO_STATUSES, get_video_for_user, update_video_status


LEASE_SECONDS = 90
ACTIVE_TASK_STATUSES = ("queued", "running")


def enqueue_video_task(db: Session, user: User, video: Video, kind: str) -> VideoTask:
    if kind not in ("process", "run", "analyze", "embed"):
        raise ValueError("unsupported video task kind")
    # Serialize admissions for this user across API instances before counting active tasks.
    lock_user_for_limits(db, user.id)
    current_status = db.scalar(select(Video.status).where(Video.id == video.id, Video.user_id == user.id))
    if current_status in ACTIVE_VIDEO_STATUSES:
        db.rollback()
        raise ApiError(t("video_already_processing"), status.HTTP_409_CONFLICT)
    active_count = db.scalar(
        select(func.count(VideoTask.id)).where(
            VideoTask.user_id == user.id,
            VideoTask.status.in_(ACTIVE_TASK_STATUSES),
        )
    ) or 0
    if active_count >= settings.max_active_video_tasks_per_user:
        db.rollback()
        raise ApiError(t("video_task_limit_reached"), status.HTTP_429_TOO_MANY_REQUESTS)
    result = db.execute(
        update(Video)
        .where(Video.id == video.id, Video.user_id == user.id, Video.status.not_in(ACTIVE_VIDEO_STATUSES))
        .values(status=VideoStatus.QUEUED.value, processing_error=None)
    )
    if result.rowcount != 1:
        db.rollback()
        raise ApiError(t("video_already_processing"), status.HTTP_409_CONFLICT)
    task = VideoTask(video_id=video.id, user_id=user.id, kind=kind, status="queued", stage="queued", attempts=0)
    db.add(task)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ApiError(t("video_already_processing"), status.HTTP_409_CONFLICT) from exc
    db.refresh(task)
    db.refresh(video)
    return task


def latest_video_task_for_user(db: Session, user: User, video_id: str) -> VideoTask | None:
    get_video_for_user(db, user, video_id)
    return db.scalar(
        select(VideoTask)
        .where(VideoTask.video_id == video_id, VideoTask.user_id == user.id)
        .order_by(VideoTask.created_at.desc(), VideoTask.id.desc())
        .limit(1)
    )


def cancel_video_task_for_user(db: Session, user: User, video_id: str) -> VideoTask:
    get_video_for_user(db, user, video_id)
    task = db.scalar(
        select(VideoTask)
        .where(VideoTask.video_id == video_id, VideoTask.user_id == user.id, VideoTask.status.in_(ACTIVE_TASK_STATUSES))
        .with_for_update()
    )
    if task is None:
        raise ApiError("没有可取消的任务", status.HTTP_409_CONFLICT)
    task.cancel_requested_at = datetime.now(UTC)
    if task.status == "queued":
        task.status = "cancelled"
        task.stage = "cancelled"
        task.finished_at = datetime.now(UTC)
        task.video.status = VideoStatus.CANCELLED.value
    db.commit()
    if task.status == "cancelled":
        _log_task_event(task, "cancelled")
    db.refresh(task)
    return task


def recover_expired_tasks(db: Session) -> int:
    now = datetime.now(UTC)
    expired = list(db.scalars(
        select(VideoTask)
        .where(VideoTask.status == "running", VideoTask.lease_expires_at < now)
        .with_for_update(skip_locked=True)
    ))
    for task in expired:
        if task.cancel_requested_at is not None:
            task.status = "cancelled"
            task.stage = "cancelled"
            task.video.status = VideoStatus.CANCELLED.value
            task.finished_at = now
        elif task.stage == "analysis" and (task.kind == "analyze" or task.video.summary is None):
            # A provider may have billed the interrupted request. Require an explicit new request.
            task.status = "failed"
            task.error = "AI 分析中断；为避免重复计费，请检查服务商后手动重试"
            task.video.status = VideoStatus.FAILED.value
            task.video.processing_error = task.error
            task.finished_at = now
        elif task.stage == "transcription" and task.video.transcript is None and task.video.audio_path and settings.asr_provider == "openai":
            task.status = "failed"
            task.error = "云端转写中断；为避免重复计费，请检查服务商后手动重试"
            task.video.status = VideoStatus.FAILED.value
            task.video.processing_error = task.error
            task.finished_at = now
        else:
            task.status = "queued"
            task.stage = "queued"
            task.error = "Worker 中断，等待恢复"
            task.worker_id = None
            task.lease_expires_at = None
            task.video.status = VideoStatus.QUEUED.value
    db.commit()
    for task in expired:
        _log_task_event(task, "recovered")
    return len(expired)


def claim_next_task(db: Session, worker_id: str) -> VideoTask | None:
    task = db.scalar(
        select(VideoTask)
        .where(VideoTask.status == "queued")
        .order_by(VideoTask.created_at, VideoTask.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if task is None:
        return None
    task.status = "running"
    task.stage = "starting"
    task.worker_id = worker_id
    task.attempts += 1
    task.started_at = datetime.now(UTC)
    task.lease_expires_at = datetime.now(UTC) + timedelta(seconds=LEASE_SECONDS)
    task.error = None
    task.video.status = VideoStatus.PROCESSING.value
    db.commit()
    db.refresh(task)
    _log_task_event(task, "claimed")
    return task


def extend_task_lease(db: Session, task_id: str, worker_id: str) -> bool:
    result = db.execute(
        update(VideoTask)
        .where(VideoTask.id == task_id, VideoTask.worker_id == worker_id, VideoTask.status == "running")
        .values(lease_expires_at=datetime.now(UTC) + timedelta(seconds=LEASE_SECONDS))
    )
    db.commit()
    return result.rowcount == 1


def execute_claimed_task(db: Session, task_id: str, worker_id: str) -> None:
    task = db.get(VideoTask, task_id)
    if task is None or task.status != "running" or task.worker_id != worker_id:
        return
    video = task.video
    try:
        if _stop_at_checkpoint(db, task, worker_id):
            return
        needs_transcript = video.transcript is None or not video.transcript.content.strip()
        if task.kind in ("process", "run") and (needs_transcript or (task.kind == "process" and task.attempts == 1)):
            if not _set_stage(db, task, worker_id, "transcription"):
                return
            update_video_status(db, video, VideoStatus.TRANSCRIBING if video.source == "upload" else VideoStatus.DOWNLOADING)
            process_video(db, video, final_status=VideoStatus.ANALYZING if task.kind == "run" else VideoStatus.COMPLETED)
        if _stop_at_checkpoint(db, task, worker_id):
            return
        if task.kind in ("run", "analyze"):
            if task.kind == "analyze" or video.summary is None:
                if not _set_stage(db, task, worker_id, "analysis"):
                    return
                update_video_status(db, video, VideoStatus.ANALYZING)
                analyze_video(db, video)
            if _stop_at_checkpoint(db, task, worker_id):
                return
        if task.kind in ("run", "embed"):
            if not _set_stage(db, task, worker_id, "embedding"):
                return
            update_video_status(db, video, VideoStatus.EMBEDDING)
            index_video(db, video)
        elif task.kind == "analyze" and video.embedding is not None:
            if not _set_stage(db, task, worker_id, "embedding"):
                return
            update_video_status(db, video, VideoStatus.EMBEDDING)
            index_video(db, video)
        if _stop_at_checkpoint(db, task, worker_id, lock=True):
            return
        video.status = VideoStatus.COMPLETED.value
        video.processing_error = None
        task.status = "succeeded"
        task.stage = "completed"
        task.finished_at = datetime.now(UTC)
        task.lease_expires_at = None
        db.commit()
        _log_task_event(task, "succeeded")
    except Exception as exc:
        db.rollback()
        logger.error("Video task event=exception task_id={} stage={} error_type={}", task_id, task.stage, type(exc).__name__)
        task = db.get(VideoTask, task_id)
        if task is None:
            return
        db.refresh(task, with_for_update=True)
        if task.status != "running" or task.worker_id != worker_id:
            db.rollback()
            return
        task.status = "failed"
        task.error = exc.message if isinstance(exc, ApiError) else task.video.processing_error or {
            "transcription": "字幕或转写失败，请检查视频来源及转写设置",
            "analysis": "AI 分析失败，请检查模型设置或服务商额度",
            "embedding": "知识库写入失败，请检查向量库服务",
        }.get(task.stage, "任务失败，请检查视频状态后重试")
        task.finished_at = datetime.now(UTC)
        task.lease_expires_at = None
        task.video.status = VideoStatus.FAILED.value
        if not task.video.processing_error:
            task.video.processing_error = task.error
        db.commit()
        _log_task_event(task, "failed")


def _set_stage(db: Session, task: VideoTask, worker_id: str, stage: str) -> bool:
    result = db.execute(
        update(VideoTask)
        .where(
            VideoTask.id == task.id,
            VideoTask.status == "running",
            VideoTask.worker_id == worker_id,
            VideoTask.lease_expires_at >= datetime.now(UTC),
        )
        .values(stage=stage)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        db.rollback()
        return False
    db.commit()
    db.refresh(task)
    _log_task_event(task, "stage_started")
    return True


def _stop_at_checkpoint(db: Session, task: VideoTask, worker_id: str, *, lock: bool = False) -> bool:
    db.refresh(task, with_for_update=lock)
    lease_expiry = task.lease_expires_at
    if lease_expiry is not None and lease_expiry.tzinfo is None:
        lease_expiry = lease_expiry.replace(tzinfo=UTC)
    if task.status != "running" or task.worker_id != worker_id or lease_expiry is None or lease_expiry < datetime.now(UTC):
        db.rollback()
        return True
    if task.cancel_requested_at is None:
        return False
    task.status = "cancelled"
    task.stage = "cancelled"
    task.finished_at = datetime.now(UTC)
    task.lease_expires_at = None
    task.video.status = VideoStatus.CANCELLED.value
    task.video.processing_error = None
    db.commit()
    _log_task_event(task, "cancelled")
    return True


def _log_task_event(task: VideoTask, event: str) -> None:
    logger.info(
        "Video task event={} task_id={} kind={} status={} stage={} attempt={}",
        event, task.id, task.kind, task.status, task.stage, task.attempts,
    )


def new_worker_id() -> str:
    return str(uuid4())
