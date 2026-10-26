from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db
from app.core.config import settings
from app.core.i18n import t
from app.core.errors import ApiError
from app.core.logging import logger
from app.models.user import User
from app.schemas.video import VideoCreate, VideoListResponse, VideoNoteUpdate, VideoProcessResponse, VideoRead, VideoTaskRead, VideoUpdate
from app.services.ai_settings import resolve_llm
from app.services.rag import build_video_document
from app.services.request_limits import consume_request, lock_user_for_limits
from app.services.video_tasks import cancel_video_task_for_user, enqueue_video_task, latest_video_task_for_user
from app.services.video_upload import save_uploaded_video, upload_policy
from app.services.videos import (
    create_video,
    delete_video_for_user,
    get_video_for_user,
    list_video_categories_for_user,
    list_videos_for_user,
    sync_video_index_for_user,
    update_note_for_user,
    update_video_for_user,
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


@router.get("/upload-policy", summary="获取视频上传限制")
def get_upload_policy(current_user: User = Depends(get_current_user)) -> dict:
    return upload_policy()


@router.post("/upload", response_model=VideoRead, status_code=status.HTTP_201_CREATED, summary="上传本地视频")
def upload_video(
    file: UploadFile = File(...),
    title: str | None = Form(default=None, max_length=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> VideoRead:
    video = save_uploaded_video(db=db, user=current_user, file=file, title=title)
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
    category: str | None = Query(default=None, min_length=1, max_length=120, title="分类"),
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


@router.get("/categories", response_model=list[str], summary="获取我的视频分类")
def list_video_categories(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[str]:
    return list_video_categories_for_user(db=db, user=current_user)


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


@router.patch("/{video_id}", response_model=VideoRead, summary="编辑我的视频资料")
def edit_video(
    video_id: str,
    payload: VideoUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> VideoRead:
    return VideoRead.model_validate(update_video_for_user(db, current_user, video_id, payload))


@router.put("/{video_id}/note", response_model=VideoRead, summary="编辑我的 Markdown 笔记")
def edit_video_note(
    video_id: str,
    payload: VideoNoteUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> VideoRead:
    return VideoRead.model_validate(update_note_for_user(db, current_user, video_id, payload))


@router.post("/{video_id}/sync-index", response_model=VideoRead, summary="重试知识库同步")
def sync_video_index(
    video_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> VideoRead:
    return VideoRead.model_validate(sync_video_index_for_user(db, current_user, video_id))


@router.delete(
    "/{video_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除我的视频",
    description="删除当前用户的视频记录、知识库向量及本地生成文件。处理中的视频不能删除。",
)
def delete_video(
    video_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    delete_video_for_user(db=db, user=current_user, video_id=video_id)


@router.post(
    "/{video_id}/process",
    response_model=VideoProcessResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="启动视频处理",
    description="触发视频下载和字幕解析。没有字幕时，会根据 ASR_PROVIDER 配置决定是否进行音频转写。",
)
def process_video(
    video_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> VideoProcessResponse:
    _reserve_video_task_request(db, current_user)
    video = get_video_for_user(db=db, user=current_user, video_id=video_id)
    task = enqueue_video_task(db, current_user, video, "process")
    _log_task_admitted(request, task.id, "process")
    return VideoProcessResponse(id=video.id, status=video.status, message=t("video_processing_started"), task_id=task.id)


@router.post(
    "/{video_id}/run",
    response_model=VideoProcessResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="一键处理视频并写入知识库",
    description="依次完成字幕处理、AI 分析和向量写入；失败后重试会复用已有转写和笔记。",
)
def run_video(
    video_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> VideoProcessResponse:
    _reserve_video_task_request(db, current_user)
    video = get_video_for_user(db=db, user=current_user, video_id=video_id)
    if video.summary is None:
        resolve_llm(current_user)
    task = enqueue_video_task(db, current_user, video, "run")
    _log_task_admitted(request, task.id, "run")
    return VideoProcessResponse(id=video.id, status=video.status, message="任务已入队，页面会自动更新进度", task_id=task.id)


@router.get("/{video_id}/task", response_model=VideoTaskRead | None, summary="获取最近视频任务")
def get_video_task(
    video_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> VideoTaskRead | None:
    task = latest_video_task_for_user(db, current_user, video_id)
    return VideoTaskRead.model_validate(task) if task is not None else None


@router.post("/{video_id}/task/cancel", response_model=VideoTaskRead, summary="取消视频任务")
def cancel_video_task(
    video_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> VideoTaskRead:
    return VideoTaskRead.model_validate(cancel_video_task_for_user(db, current_user, video_id))


@router.post(
    "/{video_id}/analyze",
    response_model=VideoProcessResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="启动 AI 分析",
    description="基于视频 transcript 调用 Video Analysis Agent，生成结构化摘要和 Markdown 笔记。",
)
def analyze_video(
    video_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> VideoProcessResponse:
    _reserve_video_task_request(db, current_user)
    video = get_video_for_user(db=db, user=current_user, video_id=video_id)
    if video.transcript is None or not video.transcript.content.strip():
        raise ApiError(t("transcript_required"), status.HTTP_400_BAD_REQUEST)
    resolve_llm(current_user)
    task = enqueue_video_task(db, current_user, video, "analyze")
    _log_task_admitted(request, task.id, "analyze")
    return VideoProcessResponse(id=video.id, status=video.status, message="AI 分析任务已入队", task_id=task.id)


@router.post(
    "/{video_id}/embed",
    response_model=VideoProcessResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="写入向量知识库",
    description="将视频 transcript、AI 摘要和 Markdown 笔记写入 ChromaDB，用于后续 RAG 问答。",
)
def embed_video(
    video_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> VideoProcessResponse:
    _reserve_video_task_request(db, current_user)
    video = get_video_for_user(db=db, user=current_user, video_id=video_id)
    if not build_video_document(video).strip():
        raise ApiError(t("embedding_source_required"), status.HTTP_400_BAD_REQUEST)
    task = enqueue_video_task(db, current_user, video, "embed")
    _log_task_admitted(request, task.id, "embed")
    return VideoProcessResponse(id=video.id, status=video.status, message="知识库写入任务已入队", task_id=task.id)


def _reserve_video_task_request(db: Session, user: User) -> None:
    lock_user_for_limits(db, user.id)
    consume_request(db, user.id, "video_task", settings.max_video_task_requests_per_minute)
    db.commit()


def _log_task_admitted(request: Request, task_id: str, kind: str) -> None:
    logger.info("Video task event=queued request_id={} task_id={} kind={}", request.state.request_id, task_id, kind)
