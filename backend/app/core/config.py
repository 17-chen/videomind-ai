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

    database_url: str = "postgresql+psycopg://videomind:videomind_dev_password@postgres:5432/videomind"

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

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.backend_cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
