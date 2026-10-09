from openai import OpenAI
from app.models.user import User
from app.services.ai_settings import resolve_llm


def get_llm_client(user: User) -> tuple[OpenAI, str]:
    api_key, base_url, model = resolve_llm(user)
    return OpenAI(api_key=api_key, base_url=base_url), model
