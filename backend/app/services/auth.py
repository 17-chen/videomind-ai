from dataclasses import dataclass

import httpx
from fastapi import status

from app.core.config import settings
from app.core.errors import ApiError


@dataclass(frozen=True)
class AuthIdentity:
    subject: str
    email: str
    display_name: str | None = None
    avatar_url: str | None = None


def decode_supabase_token(token: str) -> AuthIdentity:
    """Ask the configured Supabase Auth project to validate a user access token.

    This works with both legacy HS256 secrets and rotated asymmetric signing keys.
    The Auth endpoint is authoritative; unverified JWT claims are never used.
    """
    if not settings.supabase_url or not settings.supabase_anon_key:
        raise ApiError("服务端尚未配置 Supabase Auth", status.HTTP_503_SERVICE_UNAVAILABLE)

    try:
        response = httpx.get(
            f"{settings.supabase_url.rstrip('/')}/auth/v1/user",
            headers={
                "apikey": settings.supabase_anon_key,
                "Authorization": f"Bearer {token}",
            },
            timeout=8.0,
        )
    except httpx.RequestError as exc:
        raise ApiError("认证服务暂不可用", status.HTTP_503_SERVICE_UNAVAILABLE) from exc

    if response.status_code >= 500:
        raise ApiError("认证服务暂不可用", status.HTTP_503_SERVICE_UNAVAILABLE)
    if response.status_code != 200:
        raise ApiError("登录状态无效或已过期", status.HTTP_401_UNAUTHORIZED)

    try:
        payload = response.json()
    except ValueError as exc:
        raise ApiError("认证服务返回无效数据", status.HTTP_503_SERVICE_UNAVAILABLE) from exc
    if not isinstance(payload, dict):
        raise ApiError("认证服务返回无效数据", status.HTTP_503_SERVICE_UNAVAILABLE)

    subject = payload.get("id")
    email = payload.get("email")
    if not isinstance(subject, str) or not subject or not isinstance(email, str) or not email:
        raise ApiError("认证服务缺少用户信息", status.HTTP_401_UNAUTHORIZED)

    metadata = payload.get("user_metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    display_name = metadata.get("full_name") or metadata.get("name")
    avatar_url = metadata.get("avatar_url")
    return AuthIdentity(
        subject=subject,
        email=email,
        display_name=display_name if isinstance(display_name, str) else None,
        avatar_url=avatar_url if isinstance(avatar_url, str) else None,
    )
