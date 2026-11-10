"""Read-only operator checks. Never return paths, task IDs, or user data."""

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
import shutil
import stat
from collections.abc import Callable, Iterable

from sqlalchemy.orm import Session

from app.services.task_monitoring import task_queue_snapshot


@dataclass(frozen=True)
class OperationsThresholds:
    max_queued_seconds: int = 300
    max_expired_leases: int = 0
    max_failures_last_hour: int = 0
    min_free_mb: int = 1024

    def __post_init__(self):
        if any(value < 0 for value in asdict(self).values()):
            raise ValueError('Operational thresholds must be nonnegative')


def _existing_directory(root: Path) -> Path:
    # A configured output directory may not have been created yet. Check the
    # filesystem where it would be created, without making directories.
    while True:
        try:
            metadata = root.stat()
        except FileNotFoundError:
            if root.is_symlink():
                raise OSError('Configured storage location has a broken symlink')
            parent = root.parent
            if parent == root:
                raise
            root = parent
            continue
        if not stat.S_ISDIR(metadata.st_mode):
            raise OSError('Configured storage location is not a directory')
        return root


def operations_snapshot(
    session_factory: Callable[[], Session], *, roots: Iterable[Path],
    thresholds: OperationsThresholds, now: datetime | None = None,
) -> dict:
    """Check independent components even when another component is unavailable.

    Unknown checks dominate the exit status: a failed database read must never
    be interpreted as an empty queue. Free space covers only local filesystems,
    including cloud deployments' local staging/cache paths, not remote quotas.
    """
    now = now or datetime.now(UTC)
    alerts = []
    unavailable = []
    checks = {}
    try:
        with session_factory() as db:
            queue = task_queue_snapshot(db, now=now)
        checks['queue'] = {'status': 'ok', **queue}
        if queue['queued'] and queue['oldest_queued_seconds'] > thresholds.max_queued_seconds:
            alerts.append('queue_wait_exceeded')
        if queue['expired_leases'] > thresholds.max_expired_leases:
            alerts.append('expired_leases_exceeded')
        if queue['failed_last_hour'] > thresholds.max_failures_last_hour:
            alerts.append('recent_failures_exceeded')
        if alerts:
            checks['queue']['status'] = 'attention'
    except Exception:
        checks['queue'] = {'status': 'unavailable'}
        unavailable.append('queue_read_failed')

    filesystems = {}
    errors = 0
    for root in roots:
        try:
            directory = _existing_directory(Path(root).absolute())
            device = directory.stat().st_dev
            if device not in filesystems:
                filesystems[device] = shutil.disk_usage(directory).free
        except OSError:
            errors += 1
    if not filesystems or errors:
        unavailable.append('local_disk_read_failed')
    minimum = min(filesystems.values()) if filesystems else None
    checks['local_disk'] = {
        'status': 'unavailable' if not filesystems or errors else 'ok',
        'filesystems_checked': len(filesystems), 'read_errors': errors,
        'minimum_free_bytes': minimum,
    }
    if minimum is not None and minimum < thresholds.min_free_mb * 1024 * 1024:
        alerts.append('local_disk_free_below_minimum')
        if checks['local_disk']['status'] == 'ok':
            checks['local_disk']['status'] = 'attention'
    return {
        'checked_at': now.isoformat(),
        'status': 'unavailable' if unavailable else 'attention' if alerts else 'ok',
        'thresholds': asdict(thresholds), 'checks': checks,
        'alerts': alerts, 'unavailable': unavailable,
        'mutations_performed': False,
    }
