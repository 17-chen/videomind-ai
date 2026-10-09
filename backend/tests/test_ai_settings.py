import pytest
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
from app.models import AiSettings, User, Video, Transcript, Summary, Embedding  # noqa: F401
from app.services.ai_settings import resolve_llm, resolve_asr_key
from app.services.auth import AuthIdentity


@pytest.fixture
def api(monkeypatch):
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(settings, "auth_mode", "supabase")
    monkeypatch.setattr(settings, "user_api_key_encryption_key", Fernet.generate_key().decode())
    monkeypatch.setattr(settings, "deepseek_api_key", "owner-secret-never-use")
    monkeypatch.setattr(dependencies, "decode_supabase_token", lambda token: AuthIdentity(subject=token, email=f"{token}@example.com"))
    with Session(engine) as db:
        app.dependency_overrides[get_db] = lambda: db
        try:
            yield TestClient(app), db
        finally:
            app.dependency_overrides.pop(get_db, None)
    engine.dispose()


def headers(name):
    return {"Authorization": f"Bearer {name}"}


def test_user_keys_are_encrypted_private_and_not_replaced_by_owner_key(api):
    client, db = api
    assert client.get("/api/v1/settings/ai", headers=headers("alice")).json()["has_api_key"] is False
    user = db.query(User).filter_by(email="alice@example.com").one()
    with pytest.raises(Exception, match="请先在设置中添加"):
        resolve_llm(user)
    saved = client.put("/api/v1/settings/ai", headers=headers("alice"), json={"provider": "deepseek", "model": "deepseek-chat", "api_key": "alice-private-key"})
    assert saved.status_code == 200
    assert "alice-private-key" not in saved.text
    encrypted = db.query(AiSettings).filter_by(user_id=user.id).one().encrypted_api_key
    assert "alice-private-key" not in encrypted
    assert resolve_llm(user) == ("alice-private-key", "https://api.deepseek.com", "deepseek-chat")
    assert client.get("/api/v1/settings/ai", headers=headers("bob")).json()["has_api_key"] is False
    updated = client.put("/api/v1/settings/ai", headers=headers("alice"), json={"provider": "openai", "model": "gpt-4.1-mini", "api_key": "alice-openai-key", "asr_api_key": "alice-asr-key"})
    assert updated.status_code == 200
    assert resolve_llm(user)[0] == "alice-openai-key"
    assert resolve_asr_key(user) == "alice-asr-key"
    assert client.delete("/api/v1/settings/ai", headers=headers("alice")).status_code == 204
    with pytest.raises(Exception, match="请先在设置中添加"):
        resolve_llm(user)


def test_settings_reject_missing_first_key_and_untrusted_provider(api):
    client, _ = api
    assert client.put("/api/v1/settings/ai", headers=headers("alice"), json={"provider": "deepseek", "model": "deepseek-chat"}).status_code == 400
    assert client.put("/api/v1/settings/ai", headers=headers("alice"), json={"provider": "local", "model": "x", "api_key": "abcdefgh"}).status_code == 422


def test_analysis_and_chat_use_the_authenticated_users_model(api, monkeypatch):
    from types import SimpleNamespace
    from app.agents.video_analysis_agent import analyze_video_transcript
    from app.services import ai_provider
    from app.services.rag import generate_rag_answer
    from app.services.vector_store import VectorSearchResult

    client, db = api
    client.put("/api/v1/settings/ai", headers=headers("alice"), json={"provider": "deepseek", "model": "alice-model", "api_key": "alice-private-key"})
    client.put("/api/v1/settings/ai", headers=headers("bob"), json={"provider": "openai", "model": "bob-model", "api_key": "bob-private-key"})
    alice = db.query(User).filter_by(email="alice@example.com").one()
    bob = db.query(User).filter_by(email="bob@example.com").one()
    calls = []

    class FakeCompletions:
        def create(self, **kwargs):
            calls.append(kwargs)
            content = '{"title":"Test","summary":"Summary"}'
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])

    class FakeOpenAI:
        def __init__(self, *, api_key, base_url):
            calls.append({"api_key": api_key, "base_url": base_url})
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr(ai_provider, "OpenAI", FakeOpenAI)
    analysis, _ = analyze_video_transcript("test transcript", user=alice)
    assert analysis.title == "Test"
    assert calls[0] == {"api_key": "alice-private-key", "base_url": "https://api.deepseek.com"}
    assert calls[1]["model"] == "alice-model"

    result = VectorSearchResult(video_id="v", title="T", url="https://example.com", category=None, document="Test", distance=0.1)
    generate_rag_answer(user=bob, question="What?", results=[result], language="en")
    assert calls[2] == {"api_key": "bob-private-key", "base_url": "https://api.openai.com/v1"}
    assert calls[3]["model"] == "bob-model"
    assert "English" in calls[3]["messages"][0]["content"]
