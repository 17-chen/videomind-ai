from __future__ import annotations

from dataclasses import dataclass

from fastapi import status
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.i18n import t
from app.models.embedding import Embedding
from app.models.user import User
from app.models.video import Video
from app.services.ai_provider import get_llm_client
from app.services.vector_store import VectorSearchResult, vector_store


@dataclass(frozen=True)
class ChatSource:
    video_id: str
    title: str
    url: str
    category: str | None
    distance: float | None
    snippet: str


@dataclass(frozen=True)
class RagChatResult:
    answer: str
    sources: list[ChatSource]


def index_video(db: Session, video: Video) -> Embedding:
    document = build_video_document(video)
    if not document.strip():
        raise ApiError(t("embedding_source_required"), status.HTTP_400_BAD_REQUEST)

    title = video.summary.title if video.summary and video.summary.title else video.title or "未命名视频"
    category = video.summary.category if video.summary else None
    vector_id = f"video:{video.id}"
    vector_store.upsert_video_document(
        vector_id=vector_id,
        user_id=video.user_id,
        video_id=video.id,
        title=title,
        url=video.url,
        category=category,
        source=video.source,
        document=document,
    )

    embedding = db.query(Embedding).filter(Embedding.video_id == video.id).one_or_none()
    if embedding is None:
        embedding = Embedding(video_id=video.id, vector_id=vector_id)
        db.add(embedding)
    else:
        embedding.vector_id = vector_id
    db.commit()
    db.refresh(embedding)
    return embedding


def chat_with_videos(db: Session, user: User, question: str, limit: int, language: str = "zh") -> RagChatResult:
    _ = db
    results = vector_store.query_video_documents(user_id=user.id, query=question, limit=limit)
    if not results:
        return RagChatResult(answer="No relevant videos found in your library yet." if language == "en" else t("no_relevant_videos"), sources=[])

    sources = [_to_chat_source(result) for result in results]
    answer = generate_rag_answer(user=user, question=question, results=results, language=language)
    return RagChatResult(answer=answer, sources=sources)


def build_video_document(video: Video) -> str:
    chunks: list[str] = []
    if video.title:
        chunks.append(f"标题：{video.title}")
    if video.description:
        chunks.append(f"描述：{video.description}")
    if video.source:
        chunks.append(f"来源：{video.source}")
    if video.tags:
        chunks.append(f"用户标签：{', '.join(video.tags)}")

    if video.summary:
        summary = video.summary
        if summary.title:
            chunks.append(f"AI 标题：{summary.title}")
        chunks.append(f"一句话总结：{summary.summary}")
        if summary.category:
            chunks.append(f"分类：{summary.category}")
        if summary.keywords:
            chunks.append(f"关键词：{', '.join(summary.keywords)}")
        if summary.key_points:
            chunks.append("核心观点：\n" + "\n".join(f"- {point}" for point in summary.key_points))
        if summary.action_items:
            chunks.append("行动建议：\n" + "\n".join(f"- {item}" for item in summary.action_items))
        if summary.markdown_note:
            chunks.append(f"Markdown 笔记：\n{summary.markdown_note}")

    if video.transcript and video.transcript.content:
        chunks.append(f"转写全文：\n{video.transcript.content}")
    return "\n\n".join(chunks)


def generate_rag_answer(user: User, question: str, results: list[VectorSearchResult], language: str = "zh") -> str:
    context_blocks = []
    for index, result in enumerate(results, start=1):
        context_blocks.append(
            "\n".join(
                [
                    f"[资料 {index}]",
                    f"标题：{result.title or '未命名视频'}",
                    f"链接：{result.url}",
                    f"分类：{result.category or '未分类'}",
                    f"内容片段：{_truncate(result.document, 2500)}",
                ]
            )
        )

    prompt = "\n\n".join(context_blocks)
    client, model = get_llm_client(user)
    response_language = "English" if language == "en" else "中文"
    response = client.chat.completions.create(
        model=model,
        temperature=0.2,
        messages=[
            {
                "role": "system",
                "content": (
                    "你是 VideoMind AI 的个人视频知识库助手。"
                    f"你必须只基于用户已收藏视频资料回答，使用{response_language}，"
                    "结论清晰，必要时引用视频标题。"
                ),
            },
            {
                "role": "user",
                "content": f"用户问题：{question}\n\n可用视频资料：\n{prompt}",
            },
        ],
    )
    return response.choices[0].message.content or t("rag_answer_failed")


def _to_chat_source(result: VectorSearchResult) -> ChatSource:
    return ChatSource(
        video_id=result.video_id,
        title=result.title or "未命名视频",
        url=result.url,
        category=result.category,
        distance=result.distance,
        snippet=_truncate(result.document.replace("\n", " "), 260),
    )


def _truncate(text: str, max_length: int) -> str:
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."
