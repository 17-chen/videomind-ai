from typing import Literal
from pydantic import BaseModel, Field


class AiSettingsWrite(BaseModel):
    provider: Literal["deepseek", "openai"]
    model: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9._:/-]+$")
    api_key: str | None = Field(default=None, min_length=8, max_length=1000)
    asr_api_key: str | None = Field(default=None, min_length=8, max_length=1000)
    clear_asr_api_key: bool = False


class AiSettingsRead(BaseModel):
    provider: str | None = None
    model: str | None = None
    has_api_key: bool = False
    has_asr_api_key: bool = False
    demo_mode: bool = False
