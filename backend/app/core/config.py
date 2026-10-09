from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "VideoMind AI"
    app_env: str = "local"
    default_language: str = "zh-CN"
    log_level: str = "INFO"

    api_v1_prefix: str = "/api/v1"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    backend_cors_origins: str = "http://localhost:3000"

    secret_key: str = "change-me-in-production"
    access_token_expire_minutes: int = 10080

    auth_mode: str = "demo"
    supabase_url: str = ""
    supabase_anon_key: str = ""

    database_url: str = "postgresql+psycopg://videomind:videomind_dev_password@postgres:5432/videomind"
    auto_create_database_tables: bool = True

    chroma_mode: str = "embedded"
    chroma_persist_dir: str = "/app/storage/chroma"
    chroma_host: str = "chroma"
    chroma_port: int = 8000
    chroma_collection: str = "videomind_videos"

    demo_user_email: str = "demo@videomind.ai"
    demo_user_password_hash: str = "phase2-demo-user"

    llm_provider: str = "deepseek"
    llm_api_key: str = ""
    llm_base_url: str = "https://api.deepseek.com"
    llm_model: str = "deepseek-v4-flash"

    deepseek_api_key: str = ""
    user_api_key_encryption_key: str = ""

    embedding_provider: str = "local_hash"
    embedding_dimensions: int = 384

    asr_provider: str = "disabled"
    openai_api_key: str = ""
    openai_whisper_model: str = "whisper-1"

    video_storage_dir: str = "/app/storage/videos"
    audio_storage_dir: str = "/app/storage/audio"
    transcript_storage_dir: str = "/app/storage/transcripts"
    note_storage_dir: str = "/app/storage/notes"
    max_upload_mb: int = 1024
    video_download_timeout_seconds: int = 1800
    audio_extraction_timeout_seconds: int = 900
    video_cookie_file: str = ""
    video_http_proxy: str = ""
    video_user_agent: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.backend_cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    @property
    def uses_supabase_auth(self) -> bool:
        mode = self.auth_mode.lower()
        if mode == "supabase":
            return True
        if mode == "demo" and not self.is_production:
            return False
        raise RuntimeError("AUTH_MODE 必须为 supabase；demo 仅允许在非生产环境使用")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
