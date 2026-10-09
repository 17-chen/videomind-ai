"""One-click video processing. BackgroundTasks is local-only and is not a durable queue."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.logging import logger
from app.database.session import SessionLocal
from app.models.video import Video, VideoStatus
from app.services.analysis import analyze_video
from app.services.rag import index_video
from app.services.video_processing.errors import VideoProcessingError
from app.services.video_processing.pipeline import process_video
from app.services.videos import update_video_status


def run_video_workflow_by_id(video_id: str, user_id: str) -> None:
    db = SessionLocal()
    try:
        video = db.scalar(select(Video).where(Video.id == video_id, Video.user_id == user_id))
        if video is None:
            logger.warning("Skipping workflow for missing or unowned video {}", video_id)
            return
        run_video_workflow(db, video)
    finally:
        db.close()


def run_video_workflow(db: Session, video: Video) -> Video:
    stage = "download"
    try:
        if video.transcript is None or not video.transcript.content.strip():
            update_video_status(db, video, VideoStatus.DOWNLOADING)
            process_video(db, video, final_status=VideoStatus.ANALYZING)

        if video.summary is None:
            stage = "analysis"
            update_video_status(db, video, VideoStatus.ANALYZING)
            analyze_video(db, video)

        stage = "embedding"
        update_video_status(db, video, VideoStatus.EMBEDDING)
        index_video(db, video)
        update_video_status(db, video, VideoStatus.COMPLETED)
        logger.info("Completed one-click workflow for {}", video.id)
        return video
    except Exception as exc:
        db.rollback()
        if isinstance(exc, ApiError):
            message = exc.message
        elif isinstance(exc, VideoProcessingError):
            message = video.processing_error or "视频处理失败，请查看后端日志"
        else:
            message = {
                "download": "视频处理失败，请检查视频链接或转写设置",
                "analysis": "AI 分析失败，请检查模型设置或服务商额度",
                "embedding": "知识库写入失败，请检查向量库服务",
            }[stage]
        update_video_status(db, video, VideoStatus.FAILED, message)
        logger.error("One-click workflow failed for {} at {}: {}", video.id, stage, type(exc).__name__)
        return video
