import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_db
from app.api import dependencies
from app.core.config import settings
from app.database.base import Base
from app.main import app
from app.models import Embedding, Summary, Transcript, User, Video  # noqa: F401
from app.services.auth import AuthIdentity


@pytest.fixture
def authenticated_api(monkeypatch: pytest.MonkeyPatch):
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(settings, "auth_mode", "supabase")
    monkeypatch.setattr(
        dependencies,
        "decode_supabase_token",
        lambda token: AuthIdentity(subject=token, email=f"{token}@example.com"),
    )
    with Session(engine) as db:
        app.dependency_overrides[get_db] = lambda: db
        try:
            yield TestClient(app)
        finally:
            app.dependency_overrides.pop(get_db, None)
    engine.dispose()


def test_video_api_requires_access_token(authenticated_api: TestClient) -> None:
    response = authenticated_api.get("/api/v1/videos")
    assert response.status_code == 401


def test_video_api_hides_other_users_video(authenticated_api: TestClient) -> None:
    created = authenticated_api.post(
        "/api/v1/videos",
        headers={"Authorization": "Bearer alice"},
        json={"url": "https://www.bilibili.com/video/BV1example", "tags": []},
    )
    assert created.status_code == 201
    video_id = created.json()["id"]

    own_video = authenticated_api.get(f"/api/v1/videos/{video_id}", headers={"Authorization": "Bearer alice"})
    other_video = authenticated_api.get(f"/api/v1/videos/{video_id}", headers={"Authorization": "Bearer bob"})
    other_list = authenticated_api.get("/api/v1/videos", headers={"Authorization": "Bearer bob"})

    assert own_video.status_code == 200
    assert other_video.status_code == 404
    assert other_list.status_code == 200
    assert other_list.json()["total"] == 0


def test_one_click_route_requires_owner_and_users_model(authenticated_api: TestClient) -> None:
    created = authenticated_api.post(
        "/api/v1/videos",
        headers={"Authorization": "Bearer alice"},
        json={"url": "https://www.bilibili.com/video/BV1example", "tags": []},
    )
    video_id = created.json()["id"]
    assert authenticated_api.post(f"/api/v1/videos/{video_id}/run").status_code == 401
    assert authenticated_api.post(f"/api/v1/videos/{video_id}/run", headers={"Authorization": "Bearer bob"}).status_code == 404
    missing_model = authenticated_api.post(f"/api/v1/videos/{video_id}/run", headers={"Authorization": "Bearer alice"})
    assert missing_model.status_code == 400
    assert "设置" in missing_model.json()["detail"]
