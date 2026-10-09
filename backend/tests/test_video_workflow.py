from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.agents.video_analysis_agent import VideoAnalysisResult
from app.core.config import settings
from app.database.base import Base
from app.models import AiSettings, Embedding, Summary, Transcript, User, Video  # noqa: F401
from app.models.video import VideoStatus
from app.services import analysis, rag
from app.services.video_processing import pipeline
from app.services.video_processing.types import DownloadedVideo, SubtitleResult
from app.services.video_workflow import run_video_workflow
from app.services.videos import claim_video_operation


def test_one_click_workflow_resumes_after_index_failure(monkeypatch, tmp_path):
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(settings, "note_storage_dir", str(tmp_path / "notes"))
    calls = {"download": 0, "analysis": 0, "index": 0}
    indexed_documents = []

    def fake_download(url, video_id):
        calls["download"] += 1
        return DownloadedVideo(video_id=video_id, url=url, file_path=str(tmp_path / "video.mp4"), title="Original title")

    def fake_subtitle(video_id):
        return SubtitleResult(video_id=video_id, content="A transcript about vectors", file_path=str(tmp_path / "video.srt"))

    def fake_analysis(*, transcript, user, video_title):
        calls["analysis"] += 1
        assert transcript == "A transcript about vectors"
        return VideoAnalysisResult(title="AI title", summary="A summary about matrices"), "# AI title\n\nA summary about matrices"

    class FakeVectorStore:
        def upsert_video_document(self, **kwargs):
            calls["index"] += 1
            if calls["index"] == 1:
                raise RuntimeError("temporary vector outage")
            indexed_documents.append(kwargs["document"])

    monkeypatch.setattr(pipeline, "download_video", fake_download)
    monkeypatch.setattr(pipeline, "find_downloaded_subtitles", fake_subtitle)
    monkeypatch.setattr(analysis, "analyze_video_transcript", fake_analysis)
    monkeypatch.setattr(rag, "vector_store", FakeVectorStore())

    with Session(engine) as db:
        user = User(email="test@example.com", password_hash="demo")
        video = Video(user=user, url="https://example.com/video", status=VideoStatus.CREATED.value, tags=[])
        db.add(video)
        db.commit()
        claim_video_operation(db, video, VideoStatus.PROCESSING)
        failed = run_video_workflow(db, video)
        assert failed.status == VideoStatus.FAILED.value
        assert failed.transcript.content == "A transcript about vectors"
        assert failed.summary.title == "AI title"
        assert failed.processing_error == "知识库写入失败，请检查向量库服务"
        assert calls == {"download": 1, "analysis": 1, "index": 1}

        claim_video_operation(db, video, VideoStatus.PROCESSING)
        completed = run_video_workflow(db, video)
        assert completed.status == VideoStatus.COMPLETED.value
        assert completed.embedding.vector_id == f"video:{video.id}"
        assert calls == {"download": 1, "analysis": 1, "index": 2}
        assert "A transcript about vectors" in indexed_documents[0]
        assert "A summary about matrices" in indexed_documents[0]
        assert completed.processing_error is None
    engine.dispose()


def test_claim_rejects_duplicate_active_operation():
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        user = User(email="test@example.com", password_hash="demo")
        video = Video(user=user, url="https://example.com/video", status=VideoStatus.CREATED.value, tags=[])
        db.add(video)
        db.commit()
        claim_video_operation(db, video, VideoStatus.PROCESSING)
        from app.core.errors import ApiError
        try:
            claim_video_operation(db, video, VideoStatus.PROCESSING)
            assert False, "duplicate operation should be rejected"
        except ApiError as exc:
            assert exc.status_code == 409
    engine.dispose()
