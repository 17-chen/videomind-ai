"""API-level journey without external downloads or paid model calls."""
from types import SimpleNamespace

from cryptography.fernet import Fernet
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
from app.services import ai_provider, rag, video_workflow
from app.services.auth import AuthIdentity
from app.services.video_processing import pipeline
from app.services.video_processing.types import DownloadedVideo, SubtitleResult
from app.services.vector_store import VectorSearchResult


def test_own_key_video_to_private_chat(monkeypatch, tmp_path):
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(settings, "auth_mode", "supabase")
    monkeypatch.setattr(settings, "user_api_key_encryption_key", Fernet.generate_key().decode())
    monkeypatch.setattr(settings, "deepseek_api_key", "owner-key-must-not-be-used")
    monkeypatch.setattr(settings, "note_storage_dir", str(tmp_path / "notes"))
    monkeypatch.setattr(dependencies, "decode_supabase_token", lambda token: AuthIdentity(subject=token, email=f"{token}@example.com"))
    monkeypatch.setattr(video_workflow, "SessionLocal", lambda: Session(engine))

    def db_session():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = db_session
    calls = []
    documents = {}

    def download(url, video_id):
        calls.append("download")
        return DownloadedVideo(video_id=video_id, url=url, file_path=str(tmp_path / "video.mp4"), title="Vector lecture")

    def subtitles(video_id):
        return SubtitleResult(video_id=video_id, content="Matrices and vectors", file_path=str(tmp_path / "video.srt"))

    class FakeCompletions:
        def create(self, **kwargs):
            calls.append(("model", kwargs["model"]))
            if kwargs.get("response_format"):
                content = '{"title":"Vectors","summary":"Matrices summarize linear maps"}'
            else:
                content = "The video explains vectors and matrices."
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])

    class FakeOpenAI:
        def __init__(self, *, api_key, base_url):
            calls.append(("key", api_key, base_url))
            self.chat = SimpleNamespace(completions=FakeCompletions())

    class FakeVectorStore:
        def upsert_video_document(self, **kwargs):
            documents[kwargs["vector_id"]] = kwargs

        def query_video_documents(self, *, user_id, query, limit):
            return [
                VectorSearchResult(
                    video_id=doc["video_id"], title=doc["title"], url=doc["url"],
                    category=doc["category"], document=doc["document"], distance=0.1,
                )
                for doc in documents.values() if doc["user_id"] == user_id
            ][:limit]

    monkeypatch.setattr(pipeline, "download_video", download)
    monkeypatch.setattr(pipeline, "find_downloaded_subtitles", subtitles)
    monkeypatch.setattr(ai_provider, "OpenAI", FakeOpenAI)
    monkeypatch.setattr(rag, "vector_store", FakeVectorStore())

    def auth(name):
        return {"Authorization": f"Bearer {name}"}

    try:
        with TestClient(app) as client:
            saved = client.put("/api/v1/settings/ai", headers=auth("alice"), json={
                "provider": "deepseek", "model": "alice-model", "api_key": "alice-secret-key",
            })
            assert saved.status_code == 200
            assert "alice-secret-key" not in saved.text
            created = client.post("/api/v1/videos", headers=auth("alice"), json={
                "url": "https://www.bilibili.com/video/BV1example", "tags": [],
            })
            assert created.status_code == 201
            video_id = created.json()["id"]
            started = client.post(f"/api/v1/videos/{video_id}/run", headers=auth("alice"))
            assert started.status_code == 202
            detail = client.get(f"/api/v1/videos/{video_id}", headers=auth("alice"))
            assert detail.status_code == 200
            assert detail.json()["status"] == "completed"
            assert detail.json()["summary"]["title"] == "Vectors"
            assert calls == ["download", ("key", "alice-secret-key", "https://api.deepseek.com"), ("model", "alice-model")]
            assert len(documents) == 1
            assert "Matrices and vectors" in next(iter(documents.values()))["document"]

            own_chat = client.post("/api/v1/chat", headers=auth("alice"), json={"question": "What did I save?", "language": "en"})
            assert own_chat.status_code == 200
            assert own_chat.json()["sources"][0]["video_id"] == video_id
            assert ("key", "alice-secret-key", "https://api.deepseek.com") in calls

            other_detail = client.get(f"/api/v1/videos/{video_id}", headers=auth("bob"))
            other_chat = client.post("/api/v1/chat", headers=auth("bob"), json={"question": "What did Alice save?", "language": "en"})
            assert other_detail.status_code == 404
            assert other_chat.status_code == 200
            assert other_chat.json()["sources"] == []
            assert not any(call[0] == "key" and call[1] == "owner-key-must-not-be-used" for call in calls if isinstance(call, tuple))
    finally:
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()
