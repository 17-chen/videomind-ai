import re

from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.logging import logger
from app.main import app


def test_request_trace_uses_route_template_without_user_supplied_path_or_query():
    messages = []
    sink = logger.add(lambda message: messages.append(str(message)), format="{message}")
    try:
        client = TestClient(app)
        response = client.get("/health", headers={"Origin": "http://localhost:3000"})
        request_id = response.headers["X-Request-ID"]
        assert re.fullmatch(r"[0-9a-f]{32}", request_id)
        assert response.headers["Access-Control-Expose-Headers"] == "X-Request-ID, Retry-After"
        assert response.status_code == 200
        assert any(f"request_id={request_id}" in message and "route=/health status=200" in message for message in messages)

        secret = "sensitive-query-value"
        missing = client.get(f"/{secret}?token={secret}")
        assert missing.status_code == 404
        assert re.fullmatch(r"[0-9a-f]{32}", missing.headers["X-Request-ID"])
        assert any("route=<unmatched> status=404" in message for message in messages)
        assert all(secret not in message for message in messages)
    finally:
        logger.remove(sink)


def test_api_error_log_omits_authorization_value(monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "supabase")
    messages = []
    sink = logger.add(lambda message: messages.append(str(message)), format="{message}")
    try:
        response = TestClient(app).get("/api/v1/videos", headers={"Authorization": "Basic sensitive-token-value"})
        assert response.status_code == 401
        assert any("API error request_id=" in message and "status=401" in message for message in messages)
        assert all("sensitive-token-value" not in message for message in messages)
    finally:
        logger.remove(sink)


def test_unhandled_error_returns_request_id_without_logging_exception_message():
    secret = "provider-secret-value"

    def fail():
        raise RuntimeError(secret)

    app.add_api_route("/__trace_test_failure", fail, methods=["GET"])
    route = app.router.routes[-1]
    messages = []
    sink = logger.add(lambda message: messages.append(str(message)), format="{message}")
    try:
        response = TestClient(app).get("/__trace_test_failure")
        assert response.status_code == 500
        request_id = response.headers["X-Request-ID"]
        assert re.fullmatch(r"[0-9a-f]{32}", request_id)
        assert any(f"Unhandled error request_id={request_id} type=RuntimeError" in message for message in messages)
        assert all(secret not in message for message in messages)
    finally:
        logger.remove(sink)
        app.router.routes.remove(route)
