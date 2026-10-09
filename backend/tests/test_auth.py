import httpx
import pytest
from fastapi import status

from app.core.config import settings
from app.core.errors import ApiError
from app.services.auth import decode_supabase_token


def configure_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "supabase_url", "https://example.supabase.co")
    monkeypatch.setattr(settings, "supabase_anon_key", "public-test-key")


def test_decode_supabase_token_uses_verified_auth_response(monkeypatch: pytest.MonkeyPatch) -> None:
    configure_auth(monkeypatch)

    def fake_get(url: str, *, headers: dict[str, str], timeout: float) -> httpx.Response:
        assert url == "https://example.supabase.co/auth/v1/user"
        assert headers == {"apikey": "public-test-key", "Authorization": "Bearer signed-token"}
        assert timeout > 0
        return httpx.Response(200, json={"id": "user-1", "email": "user@example.com", "user_metadata": {"full_name": "Chen Xin"}})

    monkeypatch.setattr(httpx, "get", fake_get)
    identity = decode_supabase_token("signed-token")
    assert (identity.subject, identity.email, identity.display_name) == ("user-1", "user@example.com", "Chen Xin")


def test_decode_supabase_token_rejects_invalid_token(monkeypatch: pytest.MonkeyPatch) -> None:
    configure_auth(monkeypatch)
    monkeypatch.setattr(httpx, "get", lambda *args, **kwargs: httpx.Response(401))
    with pytest.raises(ApiError) as error:
        decode_supabase_token("invalid")
    assert error.value.status_code == status.HTTP_401_UNAUTHORIZED


def test_decode_supabase_token_requires_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "supabase_url", "")
    monkeypatch.setattr(settings, "supabase_anon_key", "")
    with pytest.raises(ApiError) as error:
        decode_supabase_token("anything")
    assert error.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


def test_decode_supabase_token_reports_auth_outage(monkeypatch: pytest.MonkeyPatch) -> None:
    configure_auth(monkeypatch)
    monkeypatch.setattr(httpx, "get", lambda *args, **kwargs: httpx.Response(503))
    with pytest.raises(ApiError) as error:
        decode_supabase_token("anything")
    assert error.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


def test_unknown_auth_mode_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "auth_mode", "suapbase")
    with pytest.raises(RuntimeError):
        _ = settings.uses_supabase_auth
