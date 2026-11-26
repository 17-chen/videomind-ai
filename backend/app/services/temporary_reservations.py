"""Opt-in cooperative admission for writers sharing one local filesystem.

Records hold byte budgets only, not media paths, users or credentials. flock
ownership, never PID/age, determines whether a reservation remains active.
"""

from contextlib import contextmanager
from contextvars import ContextVar
import os
from pathlib import Path
import re
import shutil
import stat
import time
from uuid import uuid4

try:
    import fcntl
except ImportError:  # Disabled mode must not acquire a new platform dependency.
    fcntl = None

from app.core.config import settings
from app.core.errors import ApiError
from app.core.logging import logger
from app.services.temporary_storage import FREE_SPACE_MESSAGE

UNAVAILABLE = '文件存储暂不可用，请稍后重试'
MAX_RECORDS = 4096
_descriptors: ContextVar[tuple[int, ...]] = ContextVar('temporary_reservations', default=())


def reservation_descriptors():
    """Explicitly retain leases in supervised children until those children exit."""
    return _descriptors.get()


def _open_root(path):
    path = Path(path).absolute()
    if '..' in path.parts:
        raise ValueError('Parent components are not supported')
    descriptor = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in path.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        metadata = os.fstat(descriptor)
        if metadata.st_uid != os.geteuid() or metadata.st_mode & 0o077:
            raise ValueError('Private registry directory required')
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _open_record(root, name, flags):
    descriptor = os.open(name, flags | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=root)
    try:
        metadata = os.fstat(descriptor)
        if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.geteuid()
                or metadata.st_mode & 0o077 or metadata.st_nlink != 1 or metadata.st_size > 128):
            raise ValueError('Private bounded regular record required')
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


@contextmanager
def _admission_lock(descriptor):
    deadline = time.monotonic() + 2
    while True:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except BlockingIOError:
            if time.monotonic() >= deadline:
                raise ValueError('Registry is busy') from None
            time.sleep(.01)
    try:
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)


def _active_bytes(root, device):
    total, count, active = 0, 0, 0
    with os.scandir(root) as entries:
        for entry in entries:
            if entry.name == '.lock':
                continue
            count += 1
            if count > MAX_RECORDS or not re.fullmatch(r'reservation-[0-9a-f]{32}', entry.name):
                raise ValueError('Unknown or excessive registry entries')
            try:
                descriptor = _open_record(root, entry.name, os.O_RDONLY)
            except FileNotFoundError:
                continue  # The owner may release without waiting for admission.
            try:
                raw = os.pread(descriptor, 129, 0)
                if len(raw) > 128:
                    raise ValueError('Oversized reservation record')
                fields = raw.decode('ascii').split()
                if len(fields) != 3 or fields[0] != 'v1' or not all(part.isdecimal() for part in fields[1:]):
                    raise ValueError('Invalid reservation record')
                record_device, size = map(int, fields[1:])
                if size > 2**63 - 1:
                    raise ValueError('Invalid reservation size')
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    if record_device != device:
                        raise ValueError('Reservation filesystem changed') from None
                    total += size
                    active += 1
                else:
                    # Only this implementation's valid, unlocked metadata is
                    # pruned. Never remove media, cache or unknown entries.
                    try:
                        os.unlink(entry.name, dir_fd=root)
                    except FileNotFoundError:
                        pass
            finally:
                os.close(descriptor)
    if active >= MAX_RECORDS:
        raise ValueError('Reservation registry is full')
    return total


@contextmanager
def reserve_temporary_space(directory: Path, amount: int):
    """Reserve the entire upcoming operation before any managed output is made.

    Conservative: current free bytes minus ALL active budgets must leave the
    configured floor. Used bytes are not credited back during the operation.
    Cleanup must finish before leaving this context. This is not disk quota.
    """
    if not settings.media_reservation_dir:
        yield
        return
    root = lock = reservation = None
    name = None
    try:
        try:
            if fcntl is None or not isinstance(amount, int) or not 0 <= amount <= 2**63 - 1:
                raise ValueError('Unsupported reservation')
            root = _open_root(settings.media_reservation_dir)
            device = os.fstat(root).st_dev
            if Path(directory).stat().st_dev != device:
                raise ValueError('Registry and output must share a filesystem')
            lock = _open_record(root, '.lock', os.O_RDWR | os.O_CREAT)
            if os.fstat(lock).st_size:
                raise ValueError('Invalid admission lock')
            with _admission_lock(lock):
                used = _active_bytes(root, device)
                floor = settings.min_media_free_space_mb * 1024 * 1024
                if shutil.disk_usage(directory).free - used - amount < floor:
                    raise ApiError(FREE_SPACE_MESSAGE, 507)
                name = 'reservation-' + uuid4().hex
                reservation = _open_record(root, name, os.O_RDWR | os.O_CREAT | os.O_EXCL)
                fcntl.flock(reservation, fcntl.LOCK_EX | fcntl.LOCK_NB)
                record = f'v1 {device} {amount}\n'.encode('ascii')
                if os.write(reservation, record) != len(record):
                    raise OSError('Incomplete reservation record')
        except ApiError:
            raise
        except Exception:
            raise ApiError(UNAVAILABLE, 503) from None
        token = _descriptors.set((*_descriptors.get(), reservation))
        try:
            yield
        finally:
            _descriptors.reset(token)
    finally:
        if reservation is not None:
            os.close(reservation)
            observer = None
            try:
                observer = _open_record(root, name, os.O_RDONLY)
                try:
                    fcntl.flock(observer, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    pass  # A supervised child still holds the inherited lease.
                else:
                    os.unlink(name, dir_fd=root)
            except FileNotFoundError:
                pass  # A concurrent admission already pruned this closed lease.
            except Exception:
                # A closed lease is reclaimable; do not turn a committed upload
                # into a failure just because registry cleanup was unavailable.
                logger.warning('Temporary reservation metadata cleanup deferred')
            finally:
                if observer is not None:
                    os.close(observer)
        if lock is not None:
            os.close(lock)
        if root is not None:
            os.close(root)
