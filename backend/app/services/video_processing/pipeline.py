from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ApiError
from app.core.logging import logger
from app.services.ai_settings import resolve_asr_key
from app.services.storage_quota import generate_artifacts
from app.database.session import SessionLocal
from app.models.transcript import Transcript
from app.models.video import Video, VideoStatus
from app.services.video_processing.audio import extract_audio
from app.services.video_processing.downloader import download_video
from app.services.video_processing.errors import VideoProcessingError
from app.services.video_processing.subtitles import find_downloaded_subtitles
from app.services.video_processing.transcriber import ensure_local_asr_available, transcribe_audio
from app.services.video_processing.types import DownloadedVideo


def process_video_by_id(video_id: str) -> None:
    db = SessionLocal()
    try:
        video = db.get(Video, video_id)
        if video is None:
            logger.warning("Skipping processing for missing video {}", video_id)
            return

        process_video(db=db, video=video)
    except Exception as exc:
        logger.error("Background video processing stopped for {}: {}", video_id, type(exc).__name__)
    finally:
        db.close()


def process_video(db: Session, video: Video, final_status: VideoStatus = VideoStatus.COMPLETED) -> Video:
    logger.info("Starting video processing pipeline for {}", video.id)

    try:
        if video.source == "upload":
            if not video.media_path or not Path(video.media_path).is_file():
                raise VideoProcessingError("上传的视频文件不存在，请重新上传")
            downloaded = DownloadedVideo(video_id=video.id, url=video.url, file_path=video.media_path)
        else:
            downloaded = generate_artifacts(db, video, "video", lambda: download_video(url=video.url, video_id=video.id))
        video.media_path = downloaded.file_path
        video.title = video.title or downloaded.title
        video.description = video.description or downloaded.description
        video.duration = video.duration or downloaded.duration
        video.thumbnail = video.thumbnail or downloaded.thumbnail
        video.source = video.source or downloaded.source
        db.add(video)
        db.commit()

        subtitle_result = generate_artifacts(db, video, "transcript", lambda: find_downloaded_subtitles(video_id=video.id))
        if subtitle_result is not None:
            transcript_content = subtitle_result.content
        else:
            video.status = VideoStatus.TRANSCRIBING.value
            db.add(video)
            db.commit()
            if settings.asr_provider == "faster_whisper":
                ensure_local_asr_available()
                asr_key = None
            else:
                asr_key = resolve_asr_key(video.user)
            audio = generate_artifacts(db, video, "audio", lambda: extract_audio(video_path=downloaded.file_path, video_id=video.id))
            video.audio_path = audio.file_path
            db.add(video)
            db.commit()

            transcript_result = generate_artifacts(
                db, video, "transcript",
                lambda: transcribe_audio(audio_path=audio.file_path, video_id=video.id, api_key=asr_key),
            )
            transcript_content = transcript_result.content

        transcript = _upsert_transcript(db=db, video=video, content=transcript_content)

        video.status = final_status.value
        video.processing_error = None
        video.processed_at = datetime.now(UTC)
        db.add(transcript)
        db.add(video)
        db.commit()
        db.refresh(video)
        logger.info("Completed video processing pipeline for {}", video.id)
        return video
    except ApiError as exc:
        _mark_failed(db=db, video=video, message=exc.message)
        raise
    except VideoProcessingError as exc:
        _mark_failed(db=db, video=video, message=str(exc))
        raise
    except Exception:
        _mark_failed(db=db, video=video, message="处理失败，请检查设置或稍后重试")
        raise


def _upsert_transcript(db: Session, video: Video, content: str) -> Transcript:
    transcript = video.transcript
    if transcript is None:
        transcript = Transcript(video_id=video.id, content=content)
        video.transcript = transcript
    else:
        transcript.content = content

    db.add(transcript)
    return transcript


def _mark_failed(db: Session, video: Video, message: str) -> None:
    video.status = VideoStatus.FAILED.value
    video.processing_error = message[:4000]
    db.add(video)
    db.commit()
    logger.error("Video processing failed for {}", video.id)
