from fastapi.testclient import TestClient

from app.api.v1.routes import system
from app.main import app


client = TestClient(app)


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

    response = client.get("/api/v1/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "ok"}


def test_readiness_check_reports_database_failure(monkeypatch) -> None:
    def fail_connection() -> None:
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(system, "check_database_connection", fail_connection)
    response = client.get("/api/v1/health/ready")

    assert response.status_code == 503
    assert response.json()["detail"] == "数据库尚未就绪"
