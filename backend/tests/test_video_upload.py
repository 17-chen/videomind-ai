from io import BytesIO

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.agents.video_analysis_agent import VideoAnalysisResult
from app.api import dependencies
from app.api.dependencies import get_db
from app.core.config import settings
from app.core.errors import ApiError
from app.database.base import Base
from app.main import app
from app.models import AiSettings, Embedding, Summary, Transcript, User, Video  # noqa: F401
from app.models.video import VideoStatus
from app.services import analysis, rag, video_upload, videos
from app.services.video_processing import pipeline
from app.services.video_processing.types import ExtractedAudio, TranscriptResult
from app.services.video_workflow import run_video_workflow
from app.services.vector_store import vector_store
from app.services.auth import AuthIdentity


@pytest.fixture
def upload_api(monkeypatch, tmp_path):
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(settings, "auth_mode", "supabase")
    monkeypatch.setattr(settings, "max_upload_mb", 1)
    monkeypatch.setattr(settings, "video_storage_dir", str(tmp_path / "videos"))
    monkeypatch.setattr(dependencies, "decode_supabase_token", lambda token: AuthIdentity(subject=token, email=f"{token}@example.com"))
    monkeypatch.setattr(video_upload, "_probe_video", lambda path: 12)
    monkeypatch.setattr(videos, "vector_store", vector_store)

    def db_session():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = db_session
    try:
        yield TestClient(app), engine, tmp_path
    finally:
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()


def auth(name):
    return {"Authorization": f"Bearer {name}"}


def upload(client, name="alice", contents=b"video", filename="private.mp4"):
    return client.post(
        "/api/v1/videos/upload", headers=auth(name),
        files={"file": (filename, BytesIO(contents), "video/mp4")},
    )


def test_upload_is_owned_deduplicated_and_deleted(upload_api, monkeypatch):
    client, engine, root = upload_api
    deleted = []
    monkeypatch.setattr(videos.vector_store, "delete_video_document", lambda **kwargs: deleted.append(kwargs))

    response = upload(client)
    assert response.status_code == 201
    item = response.json()
    assert item["source"] == "upload"
    assert item["status"] == "created"
    assert item["duration"] == 12
    assert item["url"] == f"upload://{item['id']}"
    saved = root / "videos" / f"{item['id']}.mp4"
    assert saved.read_bytes() == b"video"
    assert not list((root / "videos").glob("*.part"))
    assert upload(client).status_code == 409
    assert client.get(f"/api/v1/videos/{item['id']}", headers=auth("bob")).status_code == 404
    assert client.delete(f"/api/v1/videos/{item['id']}", headers=auth("bob")).status_code == 404
    assert saved.exists()
    assert upload(client, name="bob").status_code == 201
    assert client.delete(f"/api/v1/videos/{item['id']}", headers=auth("alice")).status_code == 204
    assert not saved.exists()
    assert len(deleted) == 1
    with Session(engine) as db:
        assert db.query(Video).count() == 1


def test_upload_rejects_unsupported_oversize_and_invalid_media(upload_api, monkeypatch):
    client, _, root = upload_api
    policy = client.get("/api/v1/videos/upload-policy", headers=auth("alice"))
    assert policy.status_code == 200
    assert policy.json()["max_bytes"] == 1024 * 1024
    assert policy.json()["max_user_upload_bytes"] == 5120 * 1024 * 1024
    assert upload(client, filename="fake.txt").status_code == 415
    assert upload(client, contents=b"x" * (1024 * 1024 + 1)).status_code == 413

    def reject(_path):
        raise ApiError("文件不是可读取的视频", status.HTTP_415_UNSUPPORTED_MEDIA_TYPE)

    monkeypatch.setattr(video_upload, "_probe_video", reject)
    assert upload(client).status_code == 415
    assert not list((root / "videos").glob("*"))


def test_user_upload_quota_is_isolated_and_delete_releases_bytes(upload_api, monkeypatch):
    client, _, root = upload_api
    monkeypatch.setattr(settings, "max_user_upload_mb", 1)
    first = upload(client, contents=b"a" * (700 * 1024))
    assert first.status_code == 201
    assert upload(client, contents=b"b" * (400 * 1024)).status_code == 413
    assert not list((root / "videos").glob("*.part"))
    assert upload(client, name="bob", contents=b"b" * (400 * 1024)).status_code == 201
    assert client.delete(f"/api/v1/videos/{first.json()['id']}", headers=auth("alice")).status_code == 204
    assert upload(client, contents=b"b" * (400 * 1024)).status_code == 201


def test_uploaded_video_uses_local_media_without_downloading(monkeypatch, tmp_path):
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    media = tmp_path / "video.mp4"
    media.write_bytes(b"local")
    calls = []
    monkeypatch.setattr(pipeline, "download_video", lambda **kwargs: pytest.fail("upload must not be downloaded"))
    monkeypatch.setattr(pipeline, "find_downloaded_subtitles", lambda **kwargs: None)
    monkeypatch.setattr(pipeline, "resolve_asr_key", lambda user: "own-asr-key")
    monkeypatch.setattr(pipeline, "extract_audio", lambda **kwargs: ExtractedAudio(video_id=kwargs["video_id"], file_path=str(tmp_path / "audio.mp3")))

    def transcribe(**kwargs):
        calls.append(kwargs["api_key"])
        return TranscriptResult(video_id=kwargs["video_id"], content="My recorded lesson", source="whisper")

    monkeypatch.setattr(pipeline, "transcribe_audio", transcribe)
    monkeypatch.setattr(settings, "note_storage_dir", str(tmp_path / "notes"))
    monkeypatch.setattr(analysis, "analyze_video_transcript", lambda **kwargs: (
        VideoAnalysisResult(title="Lesson notes", summary="Recorded lesson summary"), "# Lesson notes",
    ))
    indexed = []

    class RecordingVectorStore:
        def upsert_video_document(self, **kwargs):
            indexed.append(kwargs)

    monkeypatch.setattr(rag, "vector_store", RecordingVectorStore())
    with Session(engine) as db:
        user = User(email="upload@example.com", password_hash="demo")
        video = Video(user=user, url="upload://local", source="upload", status=VideoStatus.CREATED.value, media_path=str(media), tags=[])
        db.add(video)
        db.commit()
        processed = run_video_workflow(db, video)
        assert processed.status == VideoStatus.COMPLETED.value
        assert processed.transcript.content == "My recorded lesson"
        assert processed.summary.markdown_note == "# Lesson notes"
        assert processed.embedding.vector_id == f"video:{video.id}"
        assert indexed[0]["url"] == f"/videos/{video.id}"
        assert "My recorded lesson" in indexed[0]["document"]
        assert calls == ["own-asr-key"]
    engine.dispose()
