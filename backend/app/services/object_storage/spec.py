"""Server-generated immutable object addresses and bounded file reads."""

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import stat
from contextlib import contextmanager
from uuid import UUID

from app.core.errors import ApiError
from app.services.temporary_storage import stage_limit_bytes

UNAVAILABLE = '文件存储暂不可用，请稍后重试'
INTEGRITY_ERROR = '文件完整性校验失败，请稍后重试'
BLOCK_SIZE = 64 * 1024
KINDS = ('video', 'audio', 'transcript', 'note')


@dataclass(frozen=True)
class ArtifactSpec:
    id: str
    user_id: str
    video_id: str
    kind: str
    filename: str
    bucket: str
    project_fingerprint: str
    sha256: str
    size_bytes: int

    def __post_init__(self):
        for value in (self.id, self.user_id, self.video_id):
            if str(UUID(value)) != value:
                raise ValueError('Canonical artifact identifiers required')
        if (self.kind not in KINDS or len(self.filename) > 180
                or not self.filename.startswith(self.video_id + '.')
                or not re.fullmatch(r'[A-Za-z0-9_.-]+', self.filename) or '..' in self.filename
                or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,99}', self.bucket)
                or not re.fullmatch(r'[a-f0-9]{64}', self.project_fingerprint)
                or not re.fullmatch(r'[a-f0-9]{64}', self.sha256)
                or self.size_bytes < 0):
            raise ValueError('Invalid artifact metadata')

    @property
    def object_key(self):
        return f'users/{self.user_id}/videos/{self.video_id}/{self.kind}/{self.id}/{self.filename}'


@contextmanager
def open_regular_file(path: Path):
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        raise ApiError(INTEGRITY_ERROR, 409) from None
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ApiError(INTEGRITY_ERROR, 409)
        with os.fdopen(descriptor, 'rb', closefd=False) as source:
            yield source
    finally:
        os.close(descriptor)


def measure_file(path: Path) -> tuple[int, str]:
    count = 0
    digest = hashlib.sha256()
    with open_regular_file(path) as source:
        while data := source.read(BLOCK_SIZE):
            count += len(data)
            if count > stage_limit_bytes():
                raise ApiError('本次处理的临时文件超过大小上限，请使用较小的视频', 413)
            digest.update(data)
    return count, digest.hexdigest()
