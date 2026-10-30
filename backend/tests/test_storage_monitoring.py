from datetime import UTC, datetime
import json
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.base import Base
from app.models import User, Video
from app.services import storage_monitoring
from app.services.storage_quota import ARTIFACT_KINDS
from scripts import storage_status


@pytest.fixture
def storage_inventory_db():
    engine = create_engine('sqlite+pysqlite://')
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            owner = User(email='private-owner@example.com', password_hash='test')
            video = Video(user=owner, url='https://example.com/private-video', tags=[])
            db.add(video)
            db.commit()
            yield db, video
    finally:
        engine.dispose()


def test_inventory_counts_without_leaking_paths_or_reading_or_deleting_files(storage_inventory_db, monkeypatch):
    db, video = storage_inventory_db
    root = Path(settings.video_storage_dir)
    root.mkdir()
    orphan_id = str(uuid4())
    files = {
        root / f'{video.id}.mp4': b'owned',
        root / f'{orphan_id}.mp4': b'orphan',
        root / f'{orphan_id}.part': b'partial',
        root / 'private-original-name.txt': b'untouched',
    }
    staging = root / '.staging-active'
    staging.mkdir()
    files[staging / f'{video.id}.mp4'] = b'stage'
    for path, content in files.items():
        path.write_bytes(content)
    before = {path: (path.stat().st_size, path.stat().st_mtime_ns) for path in files}
    monkeypatch.setattr(Path, 'read_bytes', lambda _: pytest.fail('Inventory must not read file contents'))
    report = storage_monitoring.storage_snapshot(db, now=datetime(2026, 10, 30, tzinfo=UTC))
    counts = report['roots']['video']
    assert report['status'] == 'complete' and report['cleanup_performed'] is False
    assert report['consistency'] == 'best_effort'
    assert counts['owned_bytes'] == 5 and counts['owned_files'] == 1
    assert counts['orphan_id_bytes'] == 6 and counts['orphan_id_files'] == 1
    assert counts['pending_upload_bytes'] == 7 and counts['pending_upload_files'] == 1
    assert counts['unmanaged_bytes'] == 9 and counts['unmanaged_files'] == 1
    assert counts['staging_bytes'] == 5 and counts['staging_directories'] == 1
    assert counts['disk_free_bytes'] > 0
    serialized = json.dumps(report)
    for private_value in [video.id, video.user_id, video.user.email, video.url, str(root), orphan_id, 'private-original-name']:
        assert private_value not in serialized
    assert before == {path: (path.stat().st_size, path.stat().st_mtime_ns) for path in files}


def test_inventory_does_not_follow_symlinks_or_unknown_directories(storage_inventory_db, tmp_path):
    db, video = storage_inventory_db
    root = Path(settings.video_storage_dir)
    root.mkdir()
    external = tmp_path / 'external'
    external.mkdir()
    (external / f'{video.id}.mp4').write_bytes(b'do not count')
    (root / f'{video.id}.link').symlink_to(external / f'{video.id}.mp4')
    staged = root / '.staging-test'
    staged.mkdir()
    (staged / 'linked-directory').symlink_to(external, target_is_directory=True)
    (root / 'unknown-directory').mkdir()
    (root / 'unknown-directory' / 'file.txt').write_bytes(b'leave alone')
    report = storage_monitoring.storage_snapshot(db)
    counts = report['roots']['video']
    assert counts['symlinks'] == 2
    assert counts['owned_files'] == 0 and counts['staging_files'] == 0
    assert counts['unmanaged_directories'] == 1
    assert (external / f'{video.id}.mp4').read_bytes() == b'do not count'


def test_missing_and_duplicate_roots_are_explicit_without_double_counting(storage_inventory_db, monkeypatch):
    db, video = storage_inventory_db
    root = Path(settings.video_storage_dir)
    root.mkdir()
    (root / f'{video.id}.mp4').write_bytes(b'owned')
    monkeypatch.setattr(settings, 'audio_storage_dir', str(root))
    report = storage_monitoring.storage_snapshot(db)
    assert report['status'] == 'complete'
    assert report['roots']['audio']['duplicate_of'] == 'video'
    assert report['roots']['audio']['owned_bytes'] == 0
    assert report['roots']['note']['exists'] is False
    assert sum(item['owned_bytes'] for item in report['roots'].values()) == 5


def test_symlink_root_and_unreadable_scan_are_incomplete(storage_inventory_db, monkeypatch, tmp_path):
    db, _ = storage_inventory_db
    target = tmp_path / 'target'
    target.mkdir()
    Path(settings.video_storage_dir).symlink_to(target, target_is_directory=True)
    Path(settings.audio_storage_dir).mkdir()

    def deny(_):
        raise PermissionError('sensitive-path-in-error')

    monkeypatch.setattr(storage_monitoring.os, 'scandir', deny)
    report = storage_monitoring.storage_snapshot(db)
    assert report['status'] == 'incomplete'
    assert report['roots']['video']['symlinks'] == 1
    assert report['roots']['audio']['scan_errors'] == 1
    assert 'sensitive-path' not in json.dumps(report)


def test_cli_errors_are_sanitized_and_incomplete_returns_nonzero(monkeypatch, capsys):
    def fail():
        raise RuntimeError('private-database-secret')

    monkeypatch.setattr(storage_status, 'SessionLocal', fail)
    assert storage_status.main() == 2
    output = capsys.readouterr().out
    assert 'private-database-secret' not in output
    assert json.loads(output)['error_type'] == 'RuntimeError'


def test_cli_complete_and_incomplete_exit_codes(storage_inventory_db, monkeypatch, capsys):
    from contextlib import nullcontext

    db, _ = storage_inventory_db
    monkeypatch.setattr(storage_status, 'SessionLocal', lambda: nullcontext(db))
    assert storage_status.main() == 0
    assert json.loads(capsys.readouterr().out)['status'] == 'complete'
    for kind in ARTIFACT_KINDS:
        Path(getattr(settings, f'{kind}_storage_dir')).mkdir(exist_ok=True)
    monkeypatch.setattr(storage_monitoring.shutil, 'disk_usage', lambda _: (_ for _ in ()).throw(OSError('private-path')))
    assert storage_status.main() == 2
    assert json.loads(capsys.readouterr().out)['status'] == 'incomplete'
