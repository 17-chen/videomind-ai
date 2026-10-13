import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.errors import ApiError
from app.core.config import settings
from app.database.base import Base
from app.models import AiSettings, Embedding, Summary, Transcript, User, Video  # noqa: F401
from app.models.video import VideoStatus
from app.services.video_processing import pipeline
from app.services.video_processing.errors import VideoProcessingError
from app.services.video_processing.types import DownloadedVideo, ExtractedAudio, TranscriptResult


@pytest.fixture
def video_db():
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            user = User(email="owner@example.com", password_hash="demo")
            video = Video(user=user, url="https://example.com/video", status=VideoStatus.DOWNLOADING.value, tags=[])
            db.add(video)
            db.commit()
            yield db, video
    finally:
        engine.dispose()


def _mock_download(monkeypatch):
    monkeypatch.setattr(pipeline, "download_video", lambda url, video_id: DownloadedVideo(
        video_id=video_id, url=url, file_path="/tmp/test-video.mp4", title="Test video",
    ))
    monkeypatch.setattr(pipeline, "find_downloaded_subtitles", lambda video_id: None)


def test_no_subtitle_fails_before_audio_extraction_without_asr_key(monkeypatch, video_db):
    db, video = video_db
    _mock_download(monkeypatch)
    monkeypatch.setattr(pipeline, "resolve_asr_key", lambda user: (_ for _ in ()).throw(ApiError("需要转写密钥")))
    monkeypatch.setattr(pipeline, "extract_audio", lambda **kwargs: pytest.fail("audio extraction must not start without a key"))

    with pytest.raises(ApiError, match="需要转写密钥"):
        pipeline.process_video(db, video)
    assert video.status == VideoStatus.FAILED.value
    assert video.processing_error == "需要转写密钥"
    assert video.audio_path is None


def test_no_subtitle_transcribes_with_owners_asr_key(monkeypatch, video_db):
    db, video = video_db
    _mock_download(monkeypatch)
    events = []

    def key_for_user(user):
        assert user.id == video.user_id
        events.append("key")
        return "owners-asr-key"

    def extract_audio(video_path, video_id):
        events.append("extract")
        return ExtractedAudio(video_id=video_id, file_path="/tmp/test-audio.mp3")

    def transcribe_audio(audio_path, video_id, api_key):
        events.append("transcribe")
        assert api_key == "owners-asr-key"
        return TranscriptResult(video_id=video_id, content="Transcribed words", source="whisper")

    monkeypatch.setattr(pipeline, "resolve_asr_key", key_for_user)
    monkeypatch.setattr(pipeline, "extract_audio", extract_audio)
    monkeypatch.setattr(pipeline, "transcribe_audio", transcribe_audio)
    completed = pipeline.process_video(db, video)
    assert events == ["key", "extract", "transcribe"]
    assert completed.status == VideoStatus.COMPLETED.value
    assert completed.transcript.content == "Transcribed words"


def test_no_subtitle_uses_local_asr_without_key(monkeypatch, video_db):
    db, video = video_db
    _mock_download(monkeypatch)
    monkeypatch.setattr(settings, "asr_provider", "faster_whisper")
    monkeypatch.setattr(pipeline, "ensure_local_asr_available", lambda: None)
    monkeypatch.setattr(pipeline, "resolve_asr_key", lambda user: pytest.fail("local ASR must not need a key"))
    monkeypatch.setattr(pipeline, "extract_audio", lambda **kwargs: ExtractedAudio(video_id=video.id, file_path="/tmp/local-audio.mp3"))

    def transcribe_audio(audio_path, video_id, api_key):
        assert api_key is None
        return TranscriptResult(video_id=video_id, content="本地转写", source="faster_whisper")

    monkeypatch.setattr(pipeline, "transcribe_audio", transcribe_audio)
    completed = pipeline.process_video(db, video)
    assert completed.transcript.content == "本地转写"


def test_missing_local_asr_component_fails_before_audio_extraction(monkeypatch, video_db):
    db, video = video_db
    _mock_download(monkeypatch)
    monkeypatch.setattr(settings, "asr_provider", "faster_whisper")
    monkeypatch.setattr(
        pipeline, "ensure_local_asr_available",
        lambda: (_ for _ in ()).throw(VideoProcessingError("本地组件未安装")),
    )
    monkeypatch.setattr(pipeline, "extract_audio", lambda **kwargs: pytest.fail("audio extraction must not start"))

    with pytest.raises(VideoProcessingError, match="本地组件未安装"):
        pipeline.process_video(db, video)
    assert video.status == VideoStatus.FAILED.value
