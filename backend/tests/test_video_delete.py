import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api import dependencies
from app.api.dependencies import get_db
from app.core.config import settings
from app.core.errors import ApiError
from app.database.base import Base
from app.main import app
from app.models import AiSettings, Embedding, Summary, Transcript, User, Video  # noqa: F401
from app.models.video import VideoStatus
from app.services import videos
from app.services.auth import AuthIdentity


@pytest.fixture
def video_api(monkeypatch, tmp_path):
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(settings, "auth_mode", "supabase")
    monkeypatch.setattr(dependencies, "decode_supabase_token", lambda token: AuthIdentity(subject=token, email=f"{token}@example.com"))
    for name in ("video", "audio", "transcript", "note"):
        monkeypatch.setattr(settings, f"{name}_storage_dir", str(tmp_path / name))
    deleted_vectors = []

    class FakeVectorStore:
        fail = False

        def delete_video_document(self, *, vector_id, user_id):
            if self.fail:
                raise ApiError("向量库不可用", status.HTTP_503_SERVICE_UNAVAILABLE)
            deleted_vectors.append((vector_id, user_id))

    store = FakeVectorStore()
    monkeypatch.setattr(videos, "vector_store", store)

    def db_session():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = db_session
    try:
        with TestClient(app) as client:
            yield client, engine, store, deleted_vectors, tmp_path
    finally:
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()


def auth(name):
    return {"Authorization": f"Bearer {name}"}


def create_video(client):
    result = client.post("/api/v1/videos", headers=auth("alice"), json={
        "url": "https://www.bilibili.com/video/BV1example", "tags": [],
    })
    assert result.status_code == 201
    return result.json()["id"]


def test_delete_removes_only_owners_video_vector_and_files(video_api):
    client, engine, _, deleted_vectors, root = video_api
    video_id = create_video(client)
    with Session(engine) as db:
        video = db.get(Video, video_id)
        alice_id = video.user_id
        video.transcript = Transcript(content="private transcript")
        db.commit()

    for folder, suffix in (("video", ".mp4"), ("audio", ".mp3"), ("transcript", ".txt"), ("note", ".md")):
        directory = root / folder
        directory.mkdir()
        (directory / f"{video_id}{suffix}").write_text("private", encoding="utf-8")
        (directory / "someone-else.md").write_text("keep", encoding="utf-8")

    assert client.delete(f"/api/v1/videos/{video_id}", headers=auth("bob")).status_code == 404
    assert deleted_vectors == []
    assert client.delete(f"/api/v1/videos/{video_id}", headers=auth("alice")).status_code == 204
    assert deleted_vectors == [(f"video:{video_id}", alice_id)]
    assert client.get(f"/api/v1/videos/{video_id}", headers=auth("alice")).status_code == 404
    assert client.get("/api/v1/videos", headers=auth("alice")).json()["total"] == 0
    with Session(engine) as db:
        assert db.query(Transcript).count() == 0
    for folder, suffix in (("video", ".mp4"), ("audio", ".mp3"), ("transcript", ".txt"), ("note", ".md")):
        assert not (root / folder / f"{video_id}{suffix}").exists()
        assert (root / folder / "someone-else.md").exists()


def test_delete_rejects_active_video_and_keeps_record_when_vector_cleanup_fails(video_api):
    client, engine, store, deleted_vectors, _ = video_api
    video_id = create_video(client)
    with Session(engine) as db:
        video = db.get(Video, video_id)
        video.status = VideoStatus.ANALYZING.value
        db.commit()
    assert client.delete(f"/api/v1/videos/{video_id}", headers=auth("alice")).status_code == 409
    assert deleted_vectors == []

    with Session(engine) as db:
        video = db.get(Video, video_id)
        video.status = VideoStatus.FAILED.value
        db.commit()
    store.fail = True
    failed = client.delete(f"/api/v1/videos/{video_id}", headers=auth("alice"))
    assert failed.status_code == 503
    assert client.get(f"/api/v1/videos/{video_id}", headers=auth("alice")).status_code == 200
