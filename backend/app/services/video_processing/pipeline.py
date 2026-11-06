from datetime import UTC, datetime
from contextlib import ExitStack
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ApiError
from app.core.logging import logger
from app.services.ai_settings import resolve_asr_key
from app.services.storage_quota import generate_artifacts, artifact_input_directory
from app.services.object_storage.references import reference_id, require_object_store
from app.services.object_storage.repository import materialize_artifact, materialize_artifacts
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


def process_video(db: Session, video: Video, final_status: VideoStatus = VideoStatus.COMPLETED, *, object_store=None) -> Video:
    logger.info("Starting video processing pipeline for {}", video.id)

    try:
        with ExitStack() as resources:
            return _process_video(db, video, final_status, object_store, resources)
    except ApiError as exc:
        _mark_failed(db=db, video=video, message=exc.message)
        raise
    except VideoProcessingError as exc:
        _mark_failed(db=db, video=video, message=str(exc))
        raise
    except Exception:
        _mark_failed(db=db, video=video, message="处理失败，请检查设置或稍后重试")
        raise


def _process_video(db, video, final_status, object_store, resources):
    require_object_store(video, object_store)
    def generate(kind, producer, on_publish=None):
        return generate_artifacts(db, video, kind, producer, object_store=object_store, object_on_publish=on_publish)

    def remember_download(item):
        video.media_path = item.file_path
        video.title = video.title or item.title
        video.description = video.description or item.description
        video.duration = video.duration or item.duration
        video.thumbnail = video.thumbnail or item.thumbnail
        video.source = video.source or item.source
        db.add(video)

    def remember_audio(item):
        video.audio_path = item.file_path
        db.add(video)

    def remember_transcript(item):
        if item is not None:
            _upsert_transcript(db, video, item.content)

    uploaded = video.source == "upload"
    if uploaded:
        if object_store is not None:
            reference_id(video.media_path)  # Explicit object mode never falls back to another host's local files.
        elif not video.media_path or not Path(video.media_path).is_file():
            raise VideoProcessingError("上传的视频文件不存在，请重新上传")
        downloaded = DownloadedVideo(video_id=video.id, url=video.url, file_path=video.media_path)
    else:
        downloaded = generate("video", lambda: download_video(url=video.url, video_id=video.id), remember_download)
    if uploaded or object_store is None:
        remember_download(downloaded)
        db.commit()

    media_path = downloaded.file_path
    if object_store is not None:
        root, media = resources.enter_context(materialize_artifacts(
            db, user_id=video.user_id, video_id=video.id, kind='video',
            cache_root=Path(settings.video_storage_dir), store=object_store, required_id=reference_id(media_path),
        ))
        resources.enter_context(artifact_input_directory('video', root))
        media_path = str(media)

    subtitle_result = generate("transcript", lambda: find_downloaded_subtitles(video_id=video.id), remember_transcript)
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
        audio = generate("audio", lambda: extract_audio(video_path=media_path, video_id=video.id), remember_audio)
        if object_store is None:
            remember_audio(audio)
            db.commit()

        audio_path = audio.file_path
        if object_store is not None:
            cached_audio = resources.enter_context(materialize_artifact(
                db, user_id=video.user_id, artifact_id=reference_id(audio_path),
                cache_root=Path(settings.audio_storage_dir), store=object_store,
            ))
            audio_path = str(cached_audio)

        transcript_result = generate(
            "transcript",
            lambda: transcribe_audio(audio_path=audio_path, video_id=video.id, api_key=asr_key),
            remember_transcript,
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
