"""Store a user's video with bounded streaming and verified media content."""

import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
from uuid import uuid4

from fastapi import UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ApiError
from app.models.user import User
from app.models.video import Video, VideoStatus


UPLOAD_EXTENSIONS = (".mp4", ".webm", ".mkv", ".mov", ".m4v")
CHUNK_SIZE = 1024 * 1024


def upload_policy() -> dict:
    return {
        "max_bytes": settings.max_upload_mb * 1024 * 1024,
        "max_user_upload_bytes": settings.max_user_upload_mb * 1024 * 1024,
        "extensions": list(UPLOAD_EXTENSIONS),
    }


def _check_user_upload_quota(db: Session, user: User, incoming_bytes: int) -> None:
    # Serialize admissions across API instances before publishing the new file.
    db.execute(select(User.id).where(User.id == user.id).with_for_update()).scalar_one()
    paths = db.scalars(
        select(Video.media_path).where(Video.user_id == user.id, Video.source == "upload")
    )
    used_bytes = 0
    for path in paths:
        if path:
            try:
                used_bytes += Path(path).stat().st_size
            except FileNotFoundError:
                pass
    if used_bytes + incoming_bytes > settings.max_user_upload_mb * 1024 * 1024:
        raise ApiError("已达到个人上传视频存储上限，请先删除不需要的视频", status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)


def save_uploaded_video(db: Session, user: User, file: UploadFile, title: str | None = None) -> Video:
    filename = file.filename or ""
    extension = Path(filename).suffix.lower()
    if extension not in UPLOAD_EXTENSIONS:
        raise ApiError("仅支持 MP4、WebM、MKV、MOV 和 M4V 视频", status.HTTP_415_UNSUPPORTED_MEDIA_TYPE)
    if file.content_type and not (file.content_type.startswith("video/") or file.content_type == "application/octet-stream"):
        raise ApiError("请选择视频文件", status.HTTP_415_UNSUPPORTED_MEDIA_TYPE)

    video_id = str(uuid4())
    storage_dir = Path(settings.video_storage_dir)
    storage_dir.mkdir(parents=True, exist_ok=True)
    partial_path = storage_dir / f"{video_id}.part"
    final_path = storage_dir / f"{video_id}{extension}"
    byte_count = 0
    digest = hashlib.sha256()
    max_bytes = settings.max_upload_mb * 1024 * 1024
    committed = False
    try:
        with partial_path.open("xb") as output:
            while chunk := file.file.read(CHUNK_SIZE):
                byte_count += len(chunk)
                if byte_count > max_bytes:
                    raise ApiError(f"视频不能超过 {settings.max_upload_mb} MB", status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
                digest.update(chunk)
                output.write(chunk)
        if not byte_count:
            raise ApiError("视频文件为空", status.HTTP_415_UNSUPPORTED_MEDIA_TYPE)
        duration = _probe_video(partial_path)
        checksum = digest.hexdigest()
        if db.scalar(select(Video.id).where(Video.user_id == user.id, Video.upload_sha256 == checksum)):
            raise ApiError("你已经上传过这个视频", status.HTTP_409_CONFLICT)

        _check_user_upload_quota(db, user, byte_count)

        os.replace(partial_path, final_path)
        video = Video(
            id=video_id,
            user_id=user.id,
            url=f"upload://{video_id}",
            title=title.strip() if title and title.strip() else "本地上传的视频",
            duration=duration,
            status=VideoStatus.CREATED.value,
            source="upload",
            tags=[],
            media_path=str(final_path),
            upload_sha256=checksum,
        )
        db.add(video)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            if "uq_videos_user_upload_sha256" in str(exc.orig) or "videos.user_id, videos.upload_sha256" in str(exc.orig):
                raise ApiError("你已经上传过这个视频", status.HTTP_409_CONFLICT) from exc
            raise
        committed = True
        db.refresh(video)
        return video
    except Exception:
        if not committed:
            partial_path.unlink(missing_ok=True)
            final_path.unlink(missing_ok=True)
        raise


def _probe_video(path: Path) -> int | None:
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        raise ApiError("服务器缺少 ffprobe，无法校验视频", status.HTTP_503_SERVICE_UNAVAILABLE)
    try:
        result = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "stream=codec_type:format=duration", "-of", "json", str(path)],
            capture_output=True, text=True, check=True, timeout=30,
        )
        metadata = json.loads(result.stdout)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError) as exc:
        raise ApiError("文件不是可读取的视频", status.HTTP_415_UNSUPPORTED_MEDIA_TYPE) from exc
    if not any(stream.get("codec_type") == "video" for stream in metadata.get("streams", [])):
        raise ApiError("文件没有视频画面", status.HTTP_415_UNSUPPORTED_MEDIA_TYPE)
    try:
        duration = float(metadata.get("format", {}).get("duration", 0))
    except (TypeError, ValueError):
        duration = 0
    return round(duration) if math.isfinite(duration) and duration > 0 else None
