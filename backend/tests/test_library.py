from datetime import datetime, timezone

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
from app.models import Summary, User, Video
from app.services.auth import AuthIdentity


@pytest.fixture
def library_api(monkeypatch):
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(settings, "auth_mode", "supabase")
    monkeypatch.setattr(dependencies, "decode_supabase_token", lambda token: AuthIdentity(
        subject=token, email=f"{token}@example.com"
    ))
    with Session(engine) as db:
        alice = User(id="alice", auth_subject="alice", email="alice@example.com", password_hash="unused")
        bob = User(id="bob", auth_subject="bob", email="bob@example.com", password_hash="unused")
        db.add_all([alice, bob])
        for number in range(23):
            video = Video(
                id=f"a-{number:02d}", user_id=alice.id, url=f"https://example.com/video/{number}",
                title=f"Video {number}", created_at=datetime(2026, 10, 15, tzinfo=timezone.utc),
            )
            if number == 0:
                video.summary = Summary(title="神经网络入门", summary="基础知识", category="Research")
            elif number == 1:
                video.summary = Summary(title="机器学习", summary="讲解神经网络的训练", category="学习")
            elif number == 2:
                video.title = "进度 100%"
                video.summary = Summary(summary="普通内容", category="学习")
            elif number == 3:
                video.title = "clip_name"
                video.summary = Summary(summary="普通内容", category="")
            db.add(video)
        db.add(Video(
            id="b-01", user_id=bob.id, url="https://example.com/private", title="神经网络",
            summary=Summary(title="神经网络", summary="private", category="仅其他用户可见"),
        ))
        db.commit()

    def db_session():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = db_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()


def own_get(client, path, **kwargs):
    response = client.get(path, headers={"Authorization": "Bearer alice"}, **kwargs)
    assert response.status_code == 200
    return response.json()


def test_library_pages_have_stable_order_and_own_total(library_api):
    first = own_get(library_api, "/api/v1/videos", params={"limit": 20, "offset": 0})
    second = own_get(library_api, "/api/v1/videos", params={"limit": 20, "offset": 20})

    assert first["total"] == second["total"] == 23
    assert first["offset"] == 0
    assert second["offset"] == 20
    assert [video["id"] for video in first["items"]] == [f"a-{number:02d}" for number in range(22, 2, -1)]
    assert [video["id"] for video in second["items"]] == ["a-02", "a-01", "a-00"]


def test_search_finds_ai_title_and_summary_with_category_filter(library_api):
    matched = own_get(library_api, "/api/v1/videos", params={"search": "神经网络"})
    assert matched["total"] == 2
    assert [video["id"] for video in matched["items"]] == ["a-01", "a-00"]

    filtered = own_get(library_api, "/api/v1/videos", params={"search": "神经网络", "category": "Research"})
    assert filtered["total"] == 1
    assert filtered["items"][0]["id"] == "a-00"


@pytest.mark.parametrize(("keyword", "expected"), [("%", "a-02"), ("_", "a-03")])
def test_search_treats_wildcards_as_literal_text(library_api, keyword, expected):
    matched = own_get(library_api, "/api/v1/videos", params={"search": keyword})
    assert matched["total"] == 1
    assert matched["items"][0]["id"] == expected


def test_categories_cover_all_pages_and_require_current_user(library_api):
    assert library_api.get("/api/v1/videos/categories").status_code == 401
    assert own_get(library_api, "/api/v1/videos/categories") == ["Research", "学习"]
