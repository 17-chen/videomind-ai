from cryptography.fernet import Fernet, InvalidToken
from fastapi import status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ApiError
from app.models.ai_settings import AiSettings
from app.models.user import User
from app.schemas.ai_settings import AiSettingsRead, AiSettingsWrite

PROVIDER_URLS = {
    "deepseek": "https://api.deepseek.com",
    "openai": "https://api.openai.com/v1",
}


def _cipher() -> Fernet:
    if not settings.user_api_key_encryption_key:
        raise ApiError("服务端尚未配置用户密钥加密，请联系管理员", status.HTTP_503_SERVICE_UNAVAILABLE)
    try:
        return Fernet(settings.user_api_key_encryption_key.encode())
    except (ValueError, TypeError) as exc:
        raise ApiError("服务端用户密钥加密配置无效", status.HTTP_503_SERVICE_UNAVAILABLE) from exc


def _encrypt(secret: str) -> str:
    return _cipher().encrypt(secret.strip().encode()).decode()


def _decrypt(secret: str) -> str:
    try:
        return _cipher().decrypt(secret.encode()).decode()
    except InvalidToken as exc:
        raise ApiError("无法读取已保存的 API 密钥，请联系管理员", status.HTTP_503_SERVICE_UNAVAILABLE) from exc


def public_settings(user: User) -> AiSettingsRead:
    value = user.ai_settings
    return AiSettingsRead(
        provider=value.provider if value else None,
        model=value.model if value else None,
        has_api_key=bool(value and value.encrypted_api_key),
        has_asr_api_key=bool(value and value.encrypted_asr_api_key),
        demo_mode=not settings.uses_supabase_auth,
    )


def save_settings(db: Session, user: User, payload: AiSettingsWrite) -> AiSettingsRead:
    if not settings.uses_supabase_auth:
        raise ApiError("请先配置独立用户登录，演示模式不支持保存个人密钥", status.HTTP_403_FORBIDDEN)
    value = user.ai_settings
    api_key = payload.api_key.strip() if payload.api_key else None
    asr_key = payload.asr_api_key.strip() if payload.asr_api_key else None
    if not api_key and not value:
        raise ApiError("请先填写模型 API Key", status.HTTP_400_BAD_REQUEST)
    if payload.api_key is not None and not api_key:
        raise ApiError("API Key 不能为空", status.HTTP_400_BAD_REQUEST)
    if value and payload.provider != value.provider and not api_key:
        raise ApiError("切换服务商时请填写对应的新密钥", status.HTTP_400_BAD_REQUEST)
    if value is None:
        value = AiSettings(user_id=user.id, provider=payload.provider, model=payload.model, encrypted_api_key=_encrypt(api_key))
        db.add(value)
    else:
        value.provider = payload.provider
        value.model = payload.model
        if api_key:
            value.encrypted_api_key = _encrypt(api_key)
    if payload.clear_asr_api_key:
        value.encrypted_asr_api_key = None
    elif asr_key:
        value.encrypted_asr_api_key = _encrypt(asr_key)
    db.commit()
    db.refresh(user)
    return public_settings(user)


def delete_settings(db: Session, user: User) -> None:
    if not settings.uses_supabase_auth:
        raise ApiError("请先配置独立用户登录，演示模式不支持个人密钥", status.HTTP_403_FORBIDDEN)
    if user.ai_settings:
        db.delete(user.ai_settings)
        db.commit()
        db.expire(user, ["ai_settings"])


def resolve_llm(user: User) -> tuple[str, str, str]:
    value = user.ai_settings
    if value:
        return _decrypt(value.encrypted_api_key), PROVIDER_URLS[value.provider], value.model
    if settings.uses_supabase_auth:
        raise ApiError("请先在设置中添加自己的模型 API Key", status.HTTP_400_BAD_REQUEST)
    key = (settings.deepseek_api_key or settings.llm_api_key) if settings.llm_provider == "deepseek" else settings.llm_api_key
    if not key:
        raise ApiError("尚未配置模型 API Key", status.HTTP_400_BAD_REQUEST)
    return key, settings.llm_base_url, settings.llm_model


def resolve_asr_key(user: User) -> str:
    value = user.ai_settings
    if value and value.encrypted_asr_api_key:
        return _decrypt(value.encrypted_asr_api_key)
    if value and value.provider == "openai":
        return _decrypt(value.encrypted_api_key)
    if not settings.uses_supabase_auth and settings.openai_api_key:
        return settings.openai_api_key
    raise ApiError("视频没有字幕时需要 OpenAI 转写密钥，请先在设置中填写", status.HTTP_400_BAD_REQUEST)
