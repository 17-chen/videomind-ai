from typing import Literal
from pydantic import BaseModel, Field


class VideoEmbedResponse(BaseModel):
    id: str = Field(title="视频 ID")
    vector_id: str = Field(title="向量 ID")
    message: str = Field(title="提示消息")


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000, title="问题")
    limit: int = Field(default=5, ge=1, le=10, title="检索数量")
    language: Literal["zh", "en"] = "zh"


class ChatSource(BaseModel):
    video_id: str = Field(title="视频 ID")
    title: str = Field(title="视频标题")
    url: str = Field(title="视频链接")
    category: str | None = Field(title="分类")
    distance: float | None = Field(title="向量距离")
    snippet: str = Field(title="命中的内容片段")


class ChatResponse(BaseModel):
    answer: str = Field(title="AI 回答")
    sources: list[ChatSource] = Field(title="引用视频")
