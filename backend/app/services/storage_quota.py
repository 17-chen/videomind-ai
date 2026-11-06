"""Quota for published local artifacts; PostgreSQL serializes each user's writes.

Staging files are private to an operation and are not published until admission.
Filesystem publication and SQL commits are not a distributed transaction.
"""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import is_dataclass, replace
from pathlib import Path
import os
import stat
from tempfile import TemporaryDirectory
from typing import TypeVar

from fastapi import status
from sqlalchemy import select, inspect
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ApiError
from app.models.user import User
from app.models.video import Video
from app.services.temporary_storage import check_stage_space, ensure_free_space


ARTIFACT_KINDS = ("video", "audio", "transcript", "note")
_staging: ContextVar[dict[str, Path]] = ContextVar("artifact_staging", default={})
T = TypeVar("T")
STORAGE_LIMIT_MESSAGE = "已达到个人文件存储总量上限，请先删除不需要的视频"


def artifact_directory(kind: str) -> Path:
    return _staging.get().get(kind, Path(getattr(settings, f"{kind}_storage_dir")))


@contextmanager
def artifact_input_directory(kind: str, path: Path):
    """Use a private hydrated input group without changing global settings."""
    token = _staging.set({**_staging.get(), kind: path})
    try:
        yield path
    finally:
        _staging.reset(token)


def user_storage_bytes(db: Session, user_id: str) -> int:
    """Count ID-named files in all configured roots, including failed-task output."""
    video_ids = set(db.scalars(select(Video.id).where(Video.user_id == user_id)))
    seen: set[Path] = set()
    total = 0
    for kind in ARTIFACT_KINDS:
        root = Path(getattr(settings, f"{kind}_storage_dir")).resolve()
        if not root.exists():
            continue
        for path in root.iterdir():
            if path in seen or path.name.split(".", 1)[0] not in video_ids:
                continue
            seen.add(path)
            try:
                info = path.lstat()
            except FileNotFoundError:
                continue
            if stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
                total += info.st_size
    return total


def check_storage_quota(
    db: Session, user_id: str, incoming_bytes: int, *, replacing: tuple[Path, ...] = (),
) -> None:
    """Hold the user's row lock until the caller publishes and commits/rolls back."""
    with db.no_autoflush:
        db.execute(select(User.id).where(User.id == user_id).with_for_update()).scalar_one()
        # Until migration and upload quotas share one backend, never admit a
        # local write while this user has remote objects or uncertain intents.
        from app.services.object_storage.models import StoredArtifact
        connection = db.connection()
        schema = 'public' if connection.dialect.name == 'postgresql' else None
        if inspect(connection).has_table(StoredArtifact.__tablename__, schema=schema):
            remote = db.scalar(select(StoredArtifact.id).where(
                StoredArtifact.user_id == user_id, StoredArtifact.state != 'deleted',
            ).limit(1))
            if remote is not None:
                raise ApiError('文件存储暂不可用，请稍后重试', 503)
        used = user_storage_bytes(db, user_id)
    replaced_bytes = 0
    for path in set(replacing):
        try:
            info = path.lstat()
        except FileNotFoundError:
            continue
        if not stat.S_ISREG(info.st_mode):
            raise ApiError("文件存储路径异常，请联系管理员", status.HTTP_409_CONFLICT)
        replaced_bytes += info.st_size
    # Shrinking an existing file must remain possible even for users already over quota.
    if incoming_bytes > replaced_bytes and used - replaced_bytes + incoming_bytes > settings.max_user_storage_mb * 1024 * 1024:
        raise ApiError(STORAGE_LIMIT_MESSAGE, status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)


@contextmanager
def staging_directory(kind: str) -> Iterator[Path]:
    root = Path(getattr(settings, f"{kind}_storage_dir"))
    root.mkdir(parents=True, exist_ok=True)
    ensure_free_space(root)
    with TemporaryDirectory(prefix=".staging-", dir=root) as directory:
        path = Path(directory)
        token = _staging.set({**_staging.get(), kind: path})
        try:
            yield path
        finally:
            _staging.reset(token)


def generate_artifacts(db: Session, video: Video, kind: str, producer: Callable[[], T], *, object_store=None, object_on_publish=None) -> T:
    """Generate in staging, admit all outputs together, publish, then release the lock.

    Callers must invoke this before mutating models for the generated result. No
    database lock is held while downloading, extracting audio, or calling ASR.
    """
    with staging_directory(kind) as staged:
        result = producer()
        check_stage_space(staged)
        files = list(staged.iterdir())
        if not files:
            if object_store is not None and (result is not None or kind != 'transcript'):
                raise ApiError('生成文件路径异常，请联系管理员', 409)
            return result
        root = Path(getattr(settings, f"{kind}_storage_dir"))
        for path in files:
            if not path.name.startswith(f"{video.id}.") or not path.is_file() or path.is_symlink():
                raise ApiError("生成文件路径异常，请联系管理员", status.HTTP_409_CONFLICT)
        if object_store is not None:
            # Local import avoids a cycle: the repository reuses the quota message.
            from app.services.object_storage.repository import publish_artifacts
            from app.services.object_storage.references import artifact_reference
            result_path = getattr(result, 'file_path', None)
            staged_result = result_path and is_dataclass(result) and Path(result_path).parent == staged
            if (result_path and kind in ('video', 'audio') and not staged_result) or (staged_result and Path(result_path).name not in {path.name for path in files}):
                raise ApiError('生成文件路径异常，请联系管理员', 409)
            converted = result
            def admit(specs):
                nonlocal converted
                if staged_result:
                    spec = next(spec for spec in specs if spec.filename == Path(result_path).name)
                    converted = replace(result, file_path=artifact_reference(spec.id))
                if object_on_publish is not None:
                    object_on_publish(converted)
            publish_artifacts(db, user_id=video.user_id, video_id=video.id, kind=kind,
                              paths=files, store=object_store, replace_kind=True, on_publish=admit)
            return converted

        destinations = tuple(root / path.name for path in files)
        try:
            check_storage_quota(db, video.user_id, sum(path.stat().st_size for path in files), replacing=destinations)
            owned_video = db.scalar(
                select(Video.id).where(Video.id == video.id, Video.user_id == video.user_id).with_for_update()
            )
            if owned_video is None:
                raise ApiError("未找到该视频", status.HTTP_404_NOT_FOUND)
            for path, destination in zip(files, destinations, strict=True):
                os.replace(path, destination)
            db.commit()
        except Exception:
            db.rollback()
            raise
        # Media result paths must refer to published files, never staging directories.
        result_path = getattr(result, "file_path", None)
        if result_path and is_dataclass(result) and Path(result_path).parent == staged:
            result = replace(result, file_path=str(root / Path(result_path).name))
        return result
