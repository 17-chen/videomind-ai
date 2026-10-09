from fastapi.testclient import TestClient

from app.api.v1.routes import system
from app.main import app
from app.schemas.video import VideoCreate


client = TestClient(app)


def test_api_root_redirects_to_docs() -> None:
    response = client.get("/", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/docs"


def test_video_create_extracts_url_from_share_text() -> None:
    payload = VideoCreate(url="AI Agent 入门 https://www.bilibili.com/video/BV1example 复制打开", tags=[])

    assert str(payload.url) == "https://www.bilibili.com/video/BV1example"


def test_health_check() -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_liveness_check() -> None:
    response = client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json()["service"] == "VideoMind AI"


def test_readiness_check(monkeypatch) -> None:
    monkeypatch.setattr(system, "check_database_connection", lambda: None)
    monkeypatch.setattr(system, "check_vector_store_connection", lambda: None)

    response = client.get("/api/v1/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "ok", "vector_store": "ok"}


def test_readiness_check_reports_database_failure(monkeypatch) -> None:
    def fail_connection() -> None:
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(system, "check_database_connection", fail_connection)
    response = client.get("/api/v1/health/ready")

    assert response.status_code == 503
    assert response.json()["detail"] == "数据库尚未就绪"


def test_readiness_check_reports_vector_store_failure(monkeypatch) -> None:
    monkeypatch.setattr(system, "check_database_connection", lambda: None)
    monkeypatch.setattr(system, "check_vector_store_connection", lambda: (_ for _ in ()).throw(RuntimeError("vector unavailable")))
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 503
    assert response.json()["detail"] == "向量知识库尚未就绪"
