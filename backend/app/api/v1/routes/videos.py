from fastapi import APIRouter, BackgroundTasks, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db
from app.core.i18n import t
from app.models.user import User
from app.models.video import VideoStatus
from app.schemas.rag import VideoEmbedResponse
from app.schemas.video import VideoAnalyzeResponse, VideoCreate, VideoListResponse, VideoProcessResponse, VideoRead
from app.services.ai_settings import resolve_llm
from app.services.analysis import analyze_video as analyze_video_summary
from app.services.rag import index_video
from app.services.video_processing.pipeline import process_video_by_id
from app.services.video_workflow import run_video_workflow_by_id
from app.services.videos import (
    claim_video_operation,
    create_video,
    get_video_for_user,
    list_videos_for_user,
    mark_video_processing,
    update_video_status,
)

router = APIRouter()


@router.post(
    "",
    response_model=VideoRead,
    status_code=status.HTTP_201_CREATED,
    summary="提交视频",
    description="提交一个视频 URL，创建待处理的视频记录。",
)
def submit_video(
    payload: VideoCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> VideoRead:
    video = create_video(db=db, user=current_user, payload=payload)
    return VideoRead.model_validate(video)


@router.get(
    "",
    response_model=VideoListResponse,
    summary="获取视频列表",
    description="按分页、关键词和分类获取当前用户的视频知识库列表。",
)
def list_videos(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    limit: int = Query(default=20, ge=1, le=100, title="每页数量"),
    offset: int = Query(default=0, ge=0, title="分页偏移量"),
    search: str | None = Query(default=None, min_length=1, max_length=120, title="搜索关键词"),
    category: str | None = Query(default=None, min_length=1, max_length=80, title="分类"),
) -> VideoListResponse:
    videos, total = list_videos_for_user(
        db=db,
        user=current_user,
        limit=limit,
        offset=offset,
        search=search,
        category=category,
    )
    return VideoListResponse(
        items=[VideoRead.model_validate(video) for video in videos],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{video_id}",
    response_model=VideoRead,
    summary="获取视频详情",
    description="获取单个视频的元信息、处理状态、转写文本和摘要信息。",
)
def get_video_detail(
    video_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> VideoRead:
    video = get_video_for_user(db=db, user=current_user, video_id=video_id)
    return VideoRead.model_validate(video)


@router.post(
    "/{video_id}/process",
    response_model=VideoProcessResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="启动视频处理",
    description="触发视频下载和字幕解析。没有字幕时，会根据 ASR_PROVIDER 配置决定是否进行音频转写。",
)
def process_video(
    video_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> VideoProcessResponse:
    video = get_video_for_user(db=db, user=current_user, video_id=video_id)
    video = mark_video_processing(db=db, video=video)
    background_tasks.add_task(process_video_by_id, video.id)
    return VideoProcessResponse(id=video.id, status=video.status, message=t("video_processing_started"))


@router.post(
    "/{video_id}/run",
    response_model=VideoProcessResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="一键处理视频并写入知识库",
    description="依次完成字幕处理、AI 分析和向量写入；失败后重试会复用已有转写和笔记。",
)
def run_video(
    video_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> VideoProcessResponse:
    video = get_video_for_user(db=db, user=current_user, video_id=video_id)
    if video.summary is None:
        resolve_llm(current_user)
    video = claim_video_operation(db, video, VideoStatus.PROCESSING)
    background_tasks.add_task(run_video_workflow_by_id, video.id, current_user.id)
    return VideoProcessResponse(id=video.id, status=video.status, message="已开始完整处理，页面会自动更新进度")


@router.post(
    "/{video_id}/analyze",
    response_model=VideoAnalyzeResponse,
    summary="启动 AI 分析",
    description="基于视频 transcript 调用 Video Analysis Agent，生成结构化摘要和 Markdown 笔记。",
)
def analyze_video(
    video_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> VideoAnalyzeResponse:
    video = get_video_for_user(db=db, user=current_user, video_id=video_id)
    resolve_llm(current_user)
    claim_video_operation(db, video, VideoStatus.ANALYZING)
    try:
        summary = analyze_video_summary(db=db, video=video)
    except Exception:
        db.rollback()
        update_video_status(db, video, VideoStatus.FAILED, "AI 分析失败，请检查模型设置或服务商额度")
        raise
    update_video_status(db, video, VideoStatus.COMPLETED)
    return VideoAnalyzeResponse(id=video.id, summary=summary)


@router.post(
    "/{video_id}/embed",
    response_model=VideoEmbedResponse,
    summary="写入向量知识库",
    description="将视频 transcript、AI 摘要和 Markdown 笔记写入 ChromaDB，用于后续 RAG 问答。",
)
def embed_video(
    video_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> VideoEmbedResponse:
    video = get_video_for_user(db=db, user=current_user, video_id=video_id)
    claim_video_operation(db, video, VideoStatus.EMBEDDING)
    try:
        embedding = index_video(db=db, video=video)
    except Exception:
        db.rollback()
        update_video_status(db, video, VideoStatus.FAILED, "知识库写入失败，请检查服务状态")
        raise
    update_video_status(db, video, VideoStatus.COMPLETED)
    return VideoEmbedResponse(id=video.id, vector_id=embedding.vector_id, message=t("video_indexed"))
