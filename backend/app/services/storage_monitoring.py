"""Read-only local storage inventory. Reports counts, never filenames or identities."""

from datetime import UTC, datetime
import os
from pathlib import Path
import shutil
import stat
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.video import Video
from app.services.storage_quota import ARTIFACT_KINDS
from app.services.task_monitoring import task_queue_snapshot


CATEGORIES = ('owned', 'orphan_id', 'pending_upload', 'unmanaged', 'staging')


def _generated_id(value: str) -> bool:
    try:
        return str(UUID(value)) == value.lower()
    except ValueError:
        return False


def _count_file(report: dict, category: str, size: int) -> None:
    report[f'{category}_files'] += 1
    report[f'{category}_bytes'] += size


def _scan_directory(root: Path, video_ids: set[str], report: dict, *, staging: bool = False) -> None:
    try:
        with os.scandir(root) as entries:
            for entry in entries:
                try:
                    info = entry.stat(follow_symlinks=False)
                except OSError:
                    report['scan_errors'] += 1
                    continue
                if stat.S_ISLNK(info.st_mode):
                    report['symlinks'] += 1
                elif stat.S_ISDIR(info.st_mode):
                    if staging or entry.name.startswith('.staging-'):
                        if not staging:
                            report['staging_directories'] += 1
                        _scan_directory(Path(entry.path), video_ids, report, staging=True)
                    else:
                        # Do not recurse into unknown user directories, caches or backups.
                        report['unmanaged_directories'] += 1
                elif stat.S_ISREG(info.st_mode):
                    prefix = entry.name.split('.', 1)[0]
                    if staging:
                        category = 'staging'
                    elif prefix in video_ids and '.' in entry.name:
                        category = 'owned'
                    elif _generated_id(prefix) and '.' in entry.name:
                        category = 'pending_upload' if entry.name.endswith('.part') else 'orphan_id'
                    else:
                        category = 'unmanaged'
                    _count_file(report, category, info.st_size)
                else:
                    report['other_entries'] += 1
    except OSError:
        report['scan_errors'] += 1


def storage_snapshot(db: Session, *, now: datetime | None = None) -> dict:
    """Best-effort SQL/filesystem reconciliation; no cleanup or file reads."""
    now = now or datetime.now(UTC)
    video_ids = set(db.scalars(select(Video.id)))
    queue = task_queue_snapshot(db, now=now)
    roots = {}
    scanned: dict[Path, str] = {}
    complete = True
    for kind in ARTIFACT_KINDS:
        root = Path(getattr(settings, f'{kind}_storage_dir'))
        report = {f'{category}_{unit}': 0 for category in CATEGORIES for unit in ('files', 'bytes')}
        report.update({
            'exists': False, 'staging_directories': 0, 'unmanaged_directories': 0,
            'symlinks': 0, 'other_entries': 0, 'scan_errors': 0,
            'disk_total_bytes': None, 'disk_free_bytes': None,
        })
        roots[kind] = report
        try:
            info = root.lstat()
        except FileNotFoundError:
            continue
        except OSError:
            report['scan_errors'] += 1
            complete = False
            continue
        report['exists'] = True
        if not stat.S_ISDIR(info.st_mode):
            # Includes symlink roots: never traverse an unexpected target.
            report['scan_errors'] += 1
            if stat.S_ISLNK(info.st_mode):
                report['symlinks'] += 1
            complete = False
            continue
        canonical = root.resolve()
        if canonical in scanned:
            report['duplicate_of'] = scanned[canonical]
            continue
        scanned[canonical] = kind
        _scan_directory(root, video_ids, report)
        try:
            disk = shutil.disk_usage(root)
            report['disk_total_bytes'] = disk.total
            report['disk_free_bytes'] = disk.free
        except OSError:
            report['scan_errors'] += 1
        if report['scan_errors']:
            complete = False
    return {
        'checked_at': now.isoformat(),
        'status': 'complete' if complete else 'incomplete',
        'consistency': 'best_effort',
        'active_tasks': queue['queued'] + queue['running'],
        'cleanup_performed': False,
        'roots': roots,
    }
