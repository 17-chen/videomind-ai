import json
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field

from app.core.i18n import t
from app.models.user import User
from app.services.ai_provider import get_llm_client
from app.services.video_processing.errors import VideoProcessingError


class TimelineItem(BaseModel):
    time: str = Field(default="unknown")
    topic: str
    note: str


class VideoAnalysisResult(BaseModel):
    title: str
    summary: str
    key_points: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    category: str = "Other"
    important_quotes: list[str] = Field(default_factory=list)
    timeline: list[TimelineItem] = Field(default_factory=list)
    action_items: list[str] = Field(default_factory=list)
    difficulty_level: str = "beginner"
    target_audience: str = "普通学习者"


class VideoAnalysisState(TypedDict):
    transcript: str
    video_title: str | None
    analysis: dict[str, Any]
    markdown_note: str
    user: User


def analyze_video_transcript(transcript: str, user: User, video_title: str | None = None) -> tuple[VideoAnalysisResult, str]:
    graph = _build_graph()
    state = graph.invoke(
        {
            "user": user,
            "transcript": transcript,
            "video_title": video_title,
            "analysis": {},
            "markdown_note": "",
        }
    )
    analysis = VideoAnalysisResult.model_validate(state["analysis"])
    return analysis, state["markdown_note"]


def _build_graph():
    workflow = StateGraph(VideoAnalysisState)
    workflow.add_node("analyze_transcript", _analysis_node)
    workflow.add_node("render_markdown", _markdown_node)
    workflow.set_entry_point("analyze_transcript")
    workflow.add_edge("analyze_transcript", "render_markdown")
    workflow.add_edge("render_markdown", END)
    return workflow.compile()


def _analysis_node(state: VideoAnalysisState) -> VideoAnalysisState:
    client, model = get_llm_client(state["user"])
    prompt = _load_prompt("analysis_prompt.txt")
    title_context = f"视频原始标题：{state['video_title']}\n\n" if state.get("video_title") else ""

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": f"{title_context}Transcript:\n{state['transcript']}"},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
    except Exception as exc:
        raise VideoProcessingError(f"{t('ai_analysis_failed')}: {exc}") from exc

    content = response.choices[0].message.content or "{}"
    try:
        parsed = json.loads(content)
        analysis = VideoAnalysisResult.model_validate(parsed)
    except Exception as exc:
        raise VideoProcessingError(f"{t('ai_analysis_failed')}: LLM 返回的 JSON 无法解析") from exc

    state["analysis"] = analysis.model_dump()
    return state


def _markdown_node(state: VideoAnalysisState) -> VideoAnalysisState:
    analysis = VideoAnalysisResult.model_validate(state["analysis"])
    state["markdown_note"] = build_markdown_note(analysis)
    return state


def build_markdown_note(analysis: VideoAnalysisResult) -> str:
    key_points = "\n".join(f"{index}. {point}" for index, point in enumerate(analysis.key_points, start=1))
    quotes = "\n".join(f"- {quote}" for quote in analysis.important_quotes) or "- 暂无"
    actions = "\n".join(f"- {item}" for item in analysis.action_items) or "- 暂无"
    keywords = "、".join(analysis.keywords)
    timeline = "\n".join(
        f"- **{item.time}**：{item.topic}。{item.note}" for item in analysis.timeline
    ) or "- 暂无"

    return f"""# {analysis.title}

## 一句话总结

{analysis.summary}

## 核心观点

{key_points or "暂无"}

## 详细解析

{analysis.summary}

## 重要案例 / 引用

{quotes}

## 时间线

{timeline}

## 我的行动建议

{actions}

## 关键词

{keywords or "暂无"}

## 适合人群

{analysis.target_audience}

## 难度等级

{analysis.difficulty_level}

## 延伸阅读

- 根据关键词继续检索相关主题：{keywords or analysis.category}
"""


def _load_prompt(filename: str) -> str:
    prompt_path = Path(__file__).resolve().parents[1] / "prompts" / filename
    return prompt_path.read_text(encoding="utf-8")
