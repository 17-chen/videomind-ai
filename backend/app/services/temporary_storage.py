"""Bounds for temporary outputs, separate from retained per-user storage quotas."""

from pathlib import Path
import shutil
import stat

from fastapi import status

from app.core.config import settings
from app.core.errors import ApiError


STAGE_LIMIT_MESSAGE = '本次处理的临时文件超过大小上限，请使用较小的视频'
FREE_SPACE_MESSAGE = '服务器临时空间不足，请稍后重试'


def stage_limit_bytes() -> int:
    return settings.max_media_stage_mb * 1024 * 1024


def ensure_free_space(directory: Path, *, incoming_bytes: int = 0) -> None:
    if shutil.disk_usage(directory).free - incoming_bytes < settings.min_media_free_space_mb * 1024 * 1024:
        raise ApiError(FREE_SPACE_MESSAGE, status.HTTP_507_INSUFFICIENT_STORAGE)


def check_stage_space(directory: Path) -> None:
    """Check only the operation's private staging directory, never other users' files."""
    used = 0
    for path in directory.iterdir():
        try:
            info = path.lstat()
        except FileNotFoundError:
            # yt-dlp can remove/rename completed fragments between progress callbacks.
            continue
        if not stat.S_ISREG(info.st_mode):
            raise ApiError('生成文件路径异常，请联系管理员', status.HTTP_409_CONFLICT)
        used += info.st_size
    if used > stage_limit_bytes():
        raise ApiError(STAGE_LIMIT_MESSAGE, status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
    ensure_free_space(directory)


def write_bounded_text(path: Path, content: str) -> None:
    data = content.encode('utf-8')
    if len(data) > stage_limit_bytes():
        raise ApiError(STAGE_LIMIT_MESSAGE, status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
    path.parent.mkdir(parents=True, exist_ok=True)
    ensure_free_space(path.parent, incoming_bytes=len(data))
    path.write_bytes(data)
