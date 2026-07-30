from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class VideoCreate(BaseModel):
    url: HttpUrl = Field(title="视频链接", description="支持 Bilibili、抖音等视频 URL。")
    title: str | None = Field(default=None, max_length=500, title="标题", description="可选，未填写时由视频处理 Pipeline 自动补充。")
    description: str | None = Field(default=None, title="描述", description="可选的视频备注或原始描述。")
    tags: list[str] = Field(default_factory=list, max_length=20, title="标签", description="用户手动添加的视频标签。")


class TranscriptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, title="转写文本")

    id: str = Field(title="转写 ID")
    content: str = Field(title="转写内容")
    created_at: datetime = Field(title="创建时间")
    updated_at: datetime = Field(title="更新时间")


class SummaryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, title="AI 摘要")

    id: str = Field(title="摘要 ID")
    title: str | None = Field(title="AI 识别标题")
    summary: str = Field(title="摘要内容")
    key_points: list[str] = Field(title="核心观点")
    keywords: list[str] = Field(title="关键词")
    category: str | None = Field(title="分类")
    important_quotes: list[str] = Field(title="重要引用")
    timeline: list[dict] = Field(title="时间线")
    action_items: list[str] = Field(title="行动建议")
    difficulty_level: str | None = Field(title="难度等级")
    target_audience: str | None = Field(title="目标受众")
    analysis_json: dict = Field(title="结构化分析 JSON")
    markdown_note: str | None = Field(title="Markdown 笔记")
    created_at: datetime = Field(title="创建时间")
    updated_at: datetime = Field(title="更新时间")


class VideoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, title="视频详情")

    id: str = Field(title="视频 ID")
    user_id: str = Field(title="用户 ID")
    url: str = Field(title="视频链接")
    title: str | None = Field(title="标题")
    description: str | None = Field(title="描述")
    duration: int | None = Field(title="视频时长", description="单位：秒。")
    thumbnail: str | None = Field(title="封面图")
    status: str = Field(title="处理状态", description="机器字段，取值为 queued / processing / completed / failed。")
    source: str | None = Field(title="视频来源", description="例如 bilibili、douyin、youtube、tiktok。")
    tags: list[str] = Field(title="标签")
    processing_error: str | None = Field(title="处理错误")
    media_path: str | None = Field(title="视频文件路径")
    audio_path: str | None = Field(title="音频文件路径")
    processed_at: datetime | None = Field(title="处理完成时间")
    transcript: TranscriptRead | None = None
    summary: SummaryRead | None = None
    created_at: datetime = Field(title="创建时间")
    updated_at: datetime = Field(title="更新时间")


class VideoProcessResponse(BaseModel):
    id: str = Field(title="视频 ID")
    status: str = Field(title="处理状态")
    message: str = Field(title="提示消息")


class VideoAnalyzeResponse(BaseModel):
    id: str = Field(title="视频 ID")
    summary: SummaryRead = Field(title="AI 摘要")


class VideoListResponse(BaseModel):
    items: list[VideoRead] = Field(title="视频列表")
    total: int = Field(title="总数量")
    limit: int = Field(title="每页数量")
    offset: int = Field(title="分页偏移量")
