"""Bounded verification of a local object export, with descriptor-anchored reads."""

import hashlib
import os
from pathlib import Path
import stat

from app.services.object_storage.spec import BLOCK_SIZE, ArtifactSpec


class ObjectArchive:
    """Read-only adapter for audit_objects; never instantiates a cloud client.

    Layout: root / project_fingerprint / bucket / object_key. All components,
    including root ancestors, must be real directories, not symbolic links.
    """

    def __init__(self, root):
        if os.open not in os.supports_dir_fd or not hasattr(os, 'O_NOFOLLOW'):
            raise ValueError('Archive verification requires descriptor-relative file access')
        path = Path(root).absolute()
        if '..' in path.parts:
            raise ValueError('Archive root must not contain parent components')
        self._root = self._open_directory(path)

    @staticmethod
    def _open_directory(path):
        fd = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for part in path.parts[1:]:
                next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = next_fd
            return fd
        except BaseException:
            os.close(fd)
            raise

    def close(self):
        if self._root is not None:
            os.close(self._root)
            self._root = None

    def verify(self, spec: ArtifactSpec):
        # Revalidate even if a caller passes a forged dataclass-like object.
        spec = ArtifactSpec(**{field: getattr(spec, field) for field in ArtifactSpec.__dataclass_fields__})
        if self._root is None:
            raise ValueError('Archive is closed')
        parts = [spec.project_fingerprint, spec.bucket, *spec.object_key.split('/')]
        directory = os.dup(self._root)
        source = None
        try:
            for part in parts[:-1]:
                next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
                os.close(directory)
                directory = next_fd
            source = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            before = os.fstat(source)
            if not stat.S_ISREG(before.st_mode):
                raise ValueError('Archive entry is not a regular file')
            if before.st_size != spec.size_bytes:
                return 'mismatch'
            digest, count = hashlib.sha256(), 0
            while data := os.read(source, min(BLOCK_SIZE, spec.size_bytes + 1 - count)):
                count += len(data)
                if count > spec.size_bytes:
                    return 'mismatch'
                digest.update(data)
            after = os.fstat(source)
            current = os.stat(parts[-1], dir_fd=directory, follow_symlinks=False)
            def signature(value):
                return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns, value.st_mode)
            if signature(before) != signature(after) or signature(after) != signature(current):
                return 'mismatch'
            return 'matched' if count == spec.size_bytes and digest.hexdigest() == spec.sha256 else 'mismatch'
        except FileNotFoundError:
            return 'absent'
        finally:
            if source is not None:
                os.close(source)
            os.close(directory)
