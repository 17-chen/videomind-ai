import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api import dependencies
from app.api.dependencies import get_db
from app.core.config import settings
from app.database.base import Base
from app.main import app
from app.models import AiSettings, Embedding, Summary, Transcript, User, Video  # noqa: F401
from app.services import analysis, rag
from app.services.auth import AuthIdentity


@pytest.fixture
def edit_api(monkeypatch, tmp_path):
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(settings, "auth_mode", "supabase")
    monkeypatch.setattr(settings, "note_storage_dir", str(tmp_path))
    monkeypatch.setattr(dependencies, "decode_supabase_token", lambda token: AuthIdentity(subject=token, email=f"{token}@example.com"))
    documents = []

    class FakeStore:
        fail = False

        def upsert_video_document(self, **kwargs):
            if self.fail:
                raise RuntimeError("vector unavailable")
            documents.append(kwargs)

    store = FakeStore()
    monkeypatch.setattr(rag, "vector_store", store)

    def db_session():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = db_session
    try:
        with TestClient(app) as client:
            yield client, engine, store, documents
    finally:
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()


def auth(name):
    return {"Authorization": f"Bearer {name}"}


def create_video(client):
    response = client.post("/api/v1/videos", headers=auth("alice"), json={"url": "https://example.com/watch", "tags": []})
    assert response.status_code == 201
    return response.json()["id"]


def test_edit_owner_category_and_validation(edit_api):
    client, engine, _, _ = edit_api
    video_id = create_video(client)
    url = f"/api/v1/videos/{video_id}"
    assert client.patch(url, headers=auth("bob"), json={"title": "no"}).status_code == 404
    assert client.patch(url, headers=auth("alice"), json={"tags": ["x" * 61]}).status_code == 422
    result = client.patch(url, headers=auth("alice"), json={"title": "My title", "description": "My note", "tags": ["AI"], "category": "Study"})
    assert result.status_code == 200
    assert result.json()["user_category"] == "Study"
    assert client.get("/api/v1/videos/categories", headers=auth("alice")).json() == ["Study"]
    assert client.get("/api/v1/videos?category=Study", headers=auth("alice")).json()["total"] == 1
    assert client.get("/api/v1/videos?category=Study", headers=auth("bob")).json()["total"] == 0
    with Session(engine) as db:
        video = db.get(Video, video_id)
        video.status = "analyzing"
        db.commit()
    assert client.patch(url, headers=auth("alice"), json={"title": "busy"}).status_code == 409


def test_manual_note_survives_ai_analysis(edit_api, monkeypatch):
    client, engine, _, _ = edit_api
    video_id = create_video(client)
    with Session(engine) as db:
        video = db.get(Video, video_id)
        video.transcript = Transcript(content="original transcript")
        video.summary = Summary(summary="original", markdown_note="generated")
        db.commit()
    url = f"/api/v1/videos/{video_id}/note"
    assert client.put(url, headers=auth("bob"), json={"markdown_note": "stolen"}).status_code == 404
    assert client.put(url, headers=auth("alice"), json={"markdown_note": "hand written"}).status_code == 200

    class Result:
        title = "AI title"
        summary = "new summary"
        key_points = []
        keywords = []
        category = "AI category"
        important_quotes = []
        timeline = []
        action_items = []
        difficulty_level = None
        target_audience = None

        def model_dump(self):
            return {"summary": self.summary}

    monkeypatch.setattr(analysis, "analyze_video_transcript", lambda **kwargs: (Result(), "new generated note"))
    with Session(engine) as db:
        analysis.analyze_video(db, db.get(Video, video_id))
    detail = client.get(f"/api/v1/videos/{video_id}", headers=auth("alice")).json()
    assert detail["summary"]["markdown_note"] == "hand written"
    assert detail["summary"]["note_is_manual"] is True


def test_index_sync_failure_visible_and_retry(edit_api):
    client, engine, store, documents = edit_api
    video_id = create_video(client)
    with Session(engine) as db:
        video = db.get(Video, video_id)
        video.title = "Before edit"
        video.embedding = Embedding(vector_id=f"video:{video_id}")
        db.commit()
        rag.index_video(db, video)
    old_document = documents[-1]["document"]
    store.fail = True
    result = client.patch(f"/api/v1/videos/{video_id}", headers=auth("alice"), json={"title": "Changed"})
    assert result.status_code == 200
    assert result.json()["index_sync_error"]
    assert documents[-1]["document"] == old_document
    assert client.post(f"/api/v1/videos/{video_id}/sync-index", headers=auth("bob")).status_code == 404
    store.fail = False
    retry = client.post(f"/api/v1/videos/{video_id}/sync-index", headers=auth("alice"))
    assert retry.status_code == 200
    assert retry.json()["index_sync_error"] is None
    assert documents[-1]["title"] == "Changed"
    assert documents[-1]["document"] != old_document
