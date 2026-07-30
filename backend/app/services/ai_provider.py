from openai import OpenAI

from app.core.config import settings
from app.core.i18n import t
from app.services.video_processing.errors import VideoProcessingError


def get_llm_client() -> OpenAI:
    api_key = settings.llm_api_key
    if settings.llm_provider == "deepseek":
        api_key = settings.deepseek_api_key or api_key

    if not api_key:
        raise VideoProcessingError(t("llm_key_required"))

    return OpenAI(api_key=api_key, base_url=settings.llm_base_url)
